"""
新闻去重与事件聚类模块
三级去重：URL精确 -> 标题精确 -> 标题相似度(TF-IDF) -> 事件聚类
跨源加权：同一新闻被不同源组报道时保留多源信息用于评分
"""
import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Set

try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================
# 近似源分组：同一组内的源视为"同一来源"，跨组才算真正的"多源报道"
# 用于去重和评分时的 source_count 计算
# ============================================================
SOURCE_GROUPS: List[Set[str]] = [
    # 同花顺系
    {"同花顺", "同花顺财经"},
    # 新浪财经系
    {"新浪财经", "新浪财经API", "sina finance"},
    # RSS 系 (The Verge + HackerNews 同源配置)
    {"The Verge", "HackerNews"},
]

# 缓存：source -> group_id
_SOURCE_TO_GROUP: Dict[str, int] = {}
for _gid, _group in enumerate(SOURCE_GROUPS):
    for _src in _group:
        _SOURCE_TO_GROUP[_src] = _gid


def get_source_group(source: str) -> int:
    """获取源所属的组 ID。不在任何组中的源返回 -1（独立源）"""
    return _SOURCE_TO_GROUP.get(source, -1)


def count_unique_source_groups(items: List[Dict[str, Any]]) -> int:
    """计算新闻列表覆盖的独立源组数量"""
    groups = set()
    ungrouped = set()
    for item in items:
        src = item.get('source', '')
        gid = get_source_group(src)
        if gid >= 0:
            groups.add(gid)
        else:
            # 不在任何组中的源，各自独立计数
            ungrouped.add(src)
    return len(groups) + len(ungrouped)


def normalize_title(title: str) -> str:
    """标准化标题：去除标点、空格、数字后缀"""
    t = title.strip()
    t = re.sub(r'[【】\[\]（）\(\)「」\u3000\s]+', '', t)
    t = re.sub(r'\|.*$', '', t)  # 去除 | 后缀
    t = re.sub(r'\d+$', '', t)   # 去除末尾数字
    return t.lower()


def simple_tokenize(text: str) -> List[str]:
    """简单中文分词（jieba不可用时的回退方案）"""
    # 按常见标点/空格分词
    tokens = re.split(r'[\s\W_]+', text, flags=re.UNICODE)
    return [t for t in tokens if len(t) > 1]


def jieba_tokenize(text: str) -> List[str]:
    """jieba分词"""
    return list(jieba.cut(text))


def compute_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
    """计算两个词集合的 Jaccard 相似度"""
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def compute_tfidf_similarity(text_a: str, text_b: str) -> float:
    """基于 TF-IDF 关键词的余弦相似度"""
    if not JIEBA_AVAILABLE:
        tokens_a = simple_tokenize(text_a)
        tokens_b = simple_tokenize(text_b)
        return compute_similarity(tokens_a, tokens_b)
    
    # 提取关键词
    keywords_a = set(jieba.analyse.extract_tags(text_a, topK=10))
    keywords_b = set(jieba.analyse.extract_tags(text_b, topK=10))
    
    if not keywords_a or not keywords_b:
        tokens_a = jieba_tokenize(text_a)
        tokens_b = jieba_tokenize(text_b)
        return compute_similarity(tokens_a, tokens_b)
    
    return compute_similarity(list(keywords_a), list(keywords_b))


def extract_event_keywords(title: str, summary: str = '') -> List[str]:
    """从标题和摘要中提取事件关键词（人名、地名、机构名、核心动词）"""
    text = title + ' ' + summary
    if JIEBA_AVAILABLE:
        # 提取关键词
        keywords = jieba.analyse.extract_tags(text, topK=8)
        # 提取名词（可能的实体）
        words = jieba.lcut(text)
        entities = [w for w in words if len(w) >= 2]
        # 合并去重
        return list(set(keywords + entities))[:10]
    else:
        return simple_tokenize(text)[:10]


class NewsDeduplicator:
    """新闻去重器"""
    
    def __init__(self, title_threshold: float = 0.85, cluster_threshold: float = 0.5):
        self.title_threshold = title_threshold  # 标题相似度阈值
        self.cluster_threshold = cluster_threshold  # 事件聚类阈值
        self.seen_urls = set()
        
    def deduplicate(self, news_list: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """
        执行去重流程
        返回: (去重后的新闻列表, 被去重的新闻列表)

        关键改进：去重时保留被去重项的 source 信息到保留项的 _all_sources 字段，
        供后续评分时计算跨源加权。
        """
        if not news_list:
            return [], []

        # 每次去重重置 seen_urls，确保各次 API 调用独立（服务常驻场景）
        self.seen_urls = set()

        logger.info(f"Deduplication started: {len(news_list)} items")
        
        # 第一阶段：URL 精确去重，同时记录每个 URL 的源组
        url_sources: Dict[str, Set[str]] = defaultdict(set)
        for item in news_list:
            url = item.get('url', '')
            src = item.get('source', '')
            if url and src:
                url_sources[url].add(src)
        
        # URL 精确去重
        unique_by_url = []
        dup_by_url = []
        for item in news_list:
            url = item.get('url', '')
            if url and url in self.seen_urls:
                dup_by_url.append(item)
            else:
                if url:
                    self.seen_urls.add(url)
                # 注入 _all_sources：该 URL 被哪些源报道过
                if url and url in url_sources:
                    item['_all_sources'] = list(url_sources[url])
                unique_by_url.append(item)
        
        logger.info(f"  After URL dedup: {len(unique_by_url)} unique, {len(dup_by_url)} removed")
        
        # 标题精确去重
        seen_titles = {}
        unique_by_title = []
        dup_by_title = []
        for item in unique_by_url:
            norm_title = normalize_title(item.get('title', ''))
            if norm_title in seen_titles:
                dup_by_title.append(item)
                # 将重复项的 source 合并到保留项
                src = item.get('source', '')
                if src and '_all_sources' in seen_titles[norm_title]:
                    if src not in seen_titles[norm_title]['_all_sources']:
                        seen_titles[norm_title]['_all_sources'].append(src)
            else:
                seen_titles[norm_title] = item
                if '_all_sources' not in item:
                    item['_all_sources'] = [item.get('source', '')]
                unique_by_title.append(item)
        
        logger.info(f"  After title dedup: {len(unique_by_title)} unique, {len(dup_by_title)} removed")
        
        # 标题相似度去重
        unique_by_sim = []
        dup_by_sim = []
        title_tokens_cache = {}
        
        for item in unique_by_title:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_text = title + ' ' + summary
            
            title_tokens = jieba_tokenize(full_text) if JIEBA_AVAILABLE else simple_tokenize(full_text)
            title_tokens_cache[id(item)] = title_tokens
            
            is_dup = False
            for existing in unique_by_sim:
                existing_tokens = title_tokens_cache.get(id(existing), [])
                sim = compute_similarity(title_tokens, existing_tokens)
                if sim >= self.title_threshold:
                    is_dup = True
                    dup_by_sim.append(item)
                    # 合并 source
                    src = item.get('source', '')
                    if src:
                        if '_all_sources' not in existing:
                            existing['_all_sources'] = [existing.get('source', '')]
                        if src not in existing['_all_sources']:
                            existing['_all_sources'].append(src)
                    break
            
            if not is_dup:
                if '_all_sources' not in item:
                    item['_all_sources'] = [item.get('source', '')]
                unique_by_sim.append(item)
        
        logger.info(f"  After similarity dedup: {len(unique_by_sim)} unique, {len(dup_by_sim)} removed")
        
        all_duplicates = dup_by_url + dup_by_title + dup_by_sim
        return unique_by_sim, all_duplicates
    
    def cluster_events(self, news_list: List[Dict[str, Any]], 
                       time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """
        事件聚类：将报道同一事件的多条新闻聚合为事件簇
        返回: 事件簇列表，每个簇包含原始新闻列表
        
        新增：记录 _all_sources 用于跨源加权评分
        """
        if not news_list:
            return []
        
        logger.info(f"Event clustering started: {len(news_list)} items")
        
        clusters = []
        
        for item in news_list:
            title = item.get('title', '')
            summary = item.get('summary', '')
            keywords = extract_event_keywords(title, summary)
            
            # 尝试匹配现有簇
            matched_cluster = None
            for cluster in clusters:
                if self._belongs_to_cluster(keywords, cluster):
                    # 检查时间窗口
                    if self._within_time_window(item, cluster, time_window_hours):
                        matched_cluster = cluster
                        break
            
            if matched_cluster:
                matched_cluster['items'].append(item)
                # 更新簇的关键词
                matched_cluster['keywords'] = list(
                    set(matched_cluster['keywords']) | set(keywords)
                )
                # 合并 _all_sources
                item_sources = item.get('_all_sources', [item.get('source', '')])
                existing_sources = set(matched_cluster.get('_all_sources', []))
                existing_sources.update(item_sources)
                matched_cluster['_all_sources'] = list(existing_sources)
            else:
                item_sources = item.get('_all_sources', [item.get('source', '')])
                clusters.append({
                    'items': [item],
                    'keywords': keywords,
                    'representative_title': title,
                    'sources': list(set(item_sources)),
                    '_all_sources': list(set(item_sources)),
                    'first_seen': item.get('publishTime', ''),
                    'last_seen': item.get('publishTime', ''),
                })
        
        # 更新簇统计信息
        for cluster in clusters:
            cluster['item_count'] = len(cluster['items'])
            cluster['source_count'] = len(cluster.get('_all_sources', cluster.get('sources', [])))
        
        # 按簇大小排序
        clusters.sort(key=lambda c: c['item_count'], reverse=True)
        
        logger.info(f"Event clustering done: {len(clusters)} clusters")
        logger.info(f"  Top 3 clusters: {[c['representative_title'][:40] for c in clusters[:3]]}")
        
        return clusters
    
    def _belongs_to_cluster(self, keywords: List[str], cluster: Dict) -> bool:
        """判断新闻是否属于某个事件簇"""
        cluster_keywords = cluster['keywords']
        if not cluster_keywords:
            return False
        
        # 计算关键词重叠度
        overlap = len(set(keywords) & set(cluster_keywords))
        min_keywords = min(len(keywords), len(cluster_keywords))
        if min_keywords == 0:
            return False
        
        overlap_ratio = overlap / min_keywords
        return overlap_ratio >= self.cluster_threshold
    
    def _within_time_window(self, item: Dict, cluster: Dict, hours: int) -> bool:
        """检查新闻是否在簇的时间窗口内"""
        try:
            item_time = datetime.fromisoformat(item.get('publishTime', '').replace('Z', '+00:00').split('+')[0])
            cluster_time = datetime.fromisoformat(cluster['first_seen'].replace('Z', '+00:00').split('+')[0])
            return abs((item_time - cluster_time).total_seconds()) <= hours * 3600
        except (ValueError, AttributeError):
            return True  # 时间解析失败时默认属于同一簇
