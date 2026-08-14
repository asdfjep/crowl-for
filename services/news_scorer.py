"""
重大新闻评分引擎
综合评估新闻重要性：多源覆盖 + 关键词权重 + 地理重要性 + 事件簇规模 + 时间新鲜度
"""
import logging
import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _load_scoring_config() -> Dict[str, Any]:
    path = Path(__file__).parent.parent / "configs" / "scoring.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Failed to load scoring config {path}: {exc}")
        return {}


SCORING_CONFIG = {}

# 高权重关键词（触发加分）
# 中英文双语，覆盖航天/AI/军事/财经/显示等领域
HIGH_IMPACT_KEYWORDS = {
    # 航天
    '发射': 8, '火箭': 6, '卫星': 6, '空间站': 7, '月球': 7, '火星': 7,
    '着陆': 6, '返回': 5, '对接': 6, '变轨': 5, '载人': 7,
    'SpaceX': 7, 'Starship': 7, 'Falcon': 6, '长征': 7, '神舟': 7,
    'launch': 5, 'rocket': 5, 'orbit': 5, 'lander': 6, 'Mars': 6,
    'ISS': 5, 'mission': 4, 'NASA': 7, 'ESA': 5, 'Boeing': 5,

    # AI
    '发布': 5, '突破': 8, '开源': 5, '大模型': 6, 'AGI': 8,
    'GPT': 7, 'Claude': 6, 'Gemini': 6, '训练': 4, '参数量': 5,
    'SOTA': 6, '基准': 5, '超越': 6,
    'AI': 4, 'model': 5, 'LLM': 6, 'transformer': 5,
    'agent': 5, 'autonomous': 5, 'breakthrough': 7, 'generative': 5,
    'neural': 5, 'deep learning': 6, 'machine learning': 5,
    'Google': 4, 'Microsoft': 4, 'OpenAI': 6, 'Anthropic': 6,

    # 军事/冲突
    '战争': 9, '冲突': 8, '袭击': 9, '导弹': 9, '空袭': 9,
    '制裁': 7, '部署': 6, '演习': 5, '武器': 7, '核': 10,
    '伤亡': 8, '停火': 7, '入侵': 9,
    'war': 8, 'military': 6, 'strike': 7, 'sanction': 6,
    'nuclear': 9, 'invasion': 8, 'ceasefire': 7, 'defense': 5,

    # 财经
    '涨停': 6, '跌停': 6, '财报': 5, 'IPO': 7, '并购': 7,
    '收购': 7, '裁员': 6, '破产': 8, '暴雷': 8, '超预期': 6,
    '暴跌': 7, '暴涨': 7,
    'earnings': 5, 'revenue': 4, 'acquisition': 6, 'layoff': 6,
    'IPO': 7, 'merger': 6, 'bankruptcy': 7, 'stock': 4,
    'market': 3, 'trillion': 6, 'billion': 5,

    # 显示面板
    'OLED': 6, 'LCD': 5, '偏光片': 6, '面板': 5, '京东方': 6,
    '三星': 6, 'LG': 6, 'display': 4, 'screen': 4,
    'BOE': 5, 'TCL': 5, 'Visionox': 5,

    # 通用重大事件信号
    '重大': 7, '首次': 8, '里程碑': 7, '历史性': 8, '震惊': 6,
    '紧急': 7, '突发': 8, '独家': 5, '确认': 5,
    'first': 6, 'milestone': 7, 'historic': 7, 'breaking': 7,
    'record': 5, 'new': 3, 'announces': 4,
    'launches': 5, 'reveals': 5,
    'exclusive': 4,
}

# 地理重要性权重
GEO_WEIGHTS = {
    '中国': 7, '北京': 6, '文昌': 5, '酒泉': 5, '西昌': 5, '太原': 5,
    '美国': 7, '华盛顿': 6, 'NASA': 7, 'Kennedy': 5, 'Boca Chica': 5,
    '俄罗斯': 6, '莫斯科': 5, 'Baikonur': 5,
    '乌克兰': 8, '加沙': 8, '以色列': 7, '伊朗': 7, '中东': 8,
    '台湾': 7, '日本': 5, '韩国': 5, '印度': 5,
    '欧洲': 6, 'ESA': 6,
}

# 板块基础权重（某些板块天生更重要）
CATEGORY_BASE_WEIGHT = {
    'military': 1.3,      # 军事冲突
    'aerospace': 1.2,     # 航空航天
    'ai': 1.1,            # AI
    'economy': 1.0,       # 财经
    'polarizer': 0.9,     # 显示技术
    'politics': 1.2,      # 政治
    'tech': 1.0,          # 科技
}

DOWN_WEIGHT_KEYWORDS = {}


class NewsScorer:
    """新闻重要性评分器"""
    
    def __init__(self, now: Optional[datetime] = None, topic_config: Optional[Dict[str, Any]] = None):
        self.now = now or datetime.now()
        scoring_config = (topic_config or {}).get("scoring", {})
        self.high_impact_keywords = dict(HIGH_IMPACT_KEYWORDS)
        self.high_impact_keywords.update(scoring_config.get("high_weight", {}))
        self.category_base_weight = dict(CATEGORY_BASE_WEIGHT)
        self.category_base_weight.update(scoring_config.get("category_base_weight", {}))
        self.down_weight_keywords = scoring_config.get("down_weight", {})
        self.score_adjustments = scoring_config.get("score_adjustments", [])
    
    def score_cluster(self, cluster: Dict[str, Any]) -> float:
        """
        为事件簇评分
        返回 0-100 分
        
        跨源加权逻辑：
        - 优先使用 item._all_sources 统计实际覆盖的源组数量（排除近似源重复）
        - 同一新闻被不同源组报道 → 加权加分
        - 同一源组内的多个近似源（如同花顺+同花顺财经）只算 1 个源组
        """
        items = cluster.get('items', [])
        if not items:
            return 0.0
        
        # 取簇中所有新闻的最高分作为簇评分
        scores = [self.score_news(item) for item in items]
        base_score = max(scores) if scores else 0
        
        # 跨源覆盖加分：用 _all_sources 统计实际覆盖的源组
        # 避免同花顺/同花顺财经等近似源虚增 source_count
        all_covered_sources = set()
        for item in items:
            sources = item.get('_all_sources', [item.get('source', '')])
            for src in sources:
                all_covered_sources.add(src)
        
        # 计算独立源组数量（近似源视为一组）
        from services.deduplicator import count_unique_source_groups
        # 构造伪 items 用于计算源组
        pseudo_items = [{'source': src} for src in all_covered_sources]
        source_group_count = count_unique_source_groups(pseudo_items)
        
        # 源组加分：覆盖越多独立源组，新闻越重要
        source_bonus = min(source_group_count * 5, 25)  # 最多+25分（原为15分）
        
        # 事件簇规模加分：报道数量越多越重要
        item_count = len(items)
        cluster_bonus = min(item_count * 2, 10)  # 最多+10分
        
        final_score = base_score + source_bonus + cluster_bonus
        return min(final_score, 100.0)
    
    def score_news(self, item: Dict[str, Any]) -> float:
        """
        为单条新闻评分
        返回 0-100 分
        """
        title = item.get('title', '')
        summary = item.get('summary', '')
        category = item.get('category', '')
        location = item.get('location', '')
        publish_time_str = item.get('publishTime', '')
        tags = item.get('tags', [])
        
        full_text = f"{title} {summary} {' '.join(tags)}"
        
        # 1. 关键词权重 (0-25分)
        keyword_score = self._compute_keyword_score(full_text)
        
        # 2. 地理重要性 (0-15分)
        geo_score = self._compute_geo_score(location, full_text)
        
        # 3. 板块基础权重 (0-15分)
        category_score = self._compute_category_score(category)
        
        # 4. 时间新鲜度 (0-15分)
        time_score = self._compute_time_score(publish_time_str)
        
        # 5. 标题显著度 (0-10分) - 标题长度适中、包含数字等
        title_score = self._compute_title_score(title)
        
        # 权重重新分配（LLM 评分未接入，移除硬编码 20% 权重）
        total = (
            keyword_score * 0.3125 +
            geo_score * 0.1875 +
            category_score * 0.1875 +
            time_score * 0.1875 +
            title_score * 0.125
        )
        
        score = total * 4
        score += self._compute_config_adjustment(full_text)
        return max(0.0, min(score, 100.0))  # 归一化到0-100
    
    def _compute_keyword_score(self, text: str) -> float:
        """计算关键词匹配得分"""
        score = 0.0
        for keyword, weight in self.high_impact_keywords.items():
            if keyword.lower() in text.lower():
                score += weight
        for keyword, weight in self.down_weight_keywords.items():
            if keyword.lower() in text.lower():
                score += weight
        return max(0.0, min(score, 100.0))
    
    def _compute_geo_score(self, location: str, text: str) -> float:
        """计算地理重要性得分"""
        score = 0.0
        full_text = f"{location} {text}"
        for geo, weight in GEO_WEIGHTS.items():
            if geo.lower() in full_text.lower():
                score = max(score, weight)  # 取最高地理权重
        return score
    
    def _compute_category_score(self, category: str) -> float:
        """计算板块基础权重"""
        weight = self.category_base_weight.get(category, 1.0)
        return weight * 10  # 归一化到0-15范围

    def _compute_config_adjustment(self, text: str) -> float:
        text_lower = text.lower()
        total = 0.0
        for rule in self.score_adjustments:
            keywords = [str(k).lower() for k in rule.get("keywords", [])]
            if keywords and any(keyword in text_lower for keyword in keywords):
                total += float(rule.get("bonus", 0))
        return total
    
    def _compute_time_score(self, publish_time_str: str) -> float:
        """计算时间新鲜度得分"""
        try:
            pub_time = datetime.fromisoformat(
                publish_time_str.replace('Z', '+00:00').split('+')[0].split('.')[0]
            )
            hours_ago = (self.now - pub_time).total_seconds() / 3600
            if hours_ago < 0:
                hours_ago = 0
            # 指数衰减：0h=15分，6h=12分，12h=9分，24h=5分，48h=1分
            score = 15.0 * (0.5 ** (hours_ago / 24))
            return max(score, 0)
        except (ValueError, AttributeError):
            return 7.5  # 无法解析时给中等分
    
    def _compute_title_score(self, title: str) -> float:
        """计算标题显著度"""
        score = 0.0
        # 标题长度适中（10-50字）加分
        if 10 <= len(title) <= 50:
            score += 3
        # 包含数字（数据/统计）加分
        if re.search(r'\d+', title):
            score += 3
        # 包含感叹号或问号（紧急/重大）加分
        if '!' in title or '！' in title or '?' in title:
            score += 2
        # 全大写（英文标题强调）加分
        if title.isupper() and len(title) > 5:
            score += 2
        return min(score, 10.0)
    
    def rank_clusters(self, clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为事件簇评分并排序"""
        for cluster in clusters:
            cluster['importance_score'] = self.score_cluster(cluster)
        
        clusters.sort(key=lambda c: c['importance_score'], reverse=True)
        return clusters
    
    def rank_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为新闻列表评分并排序"""
        for item in news_list:
            item['importance_score'] = self.score_news(item)
        
        news_list.sort(key=lambda x: x['importance_score'], reverse=True)
        return news_list
