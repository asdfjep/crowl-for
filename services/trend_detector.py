"""
行业趋势信号检测模块
检测三种信号：
1. 连续报道 — 同一实体连续多日被报道
2. 热度骤升 — 今日报道量 ≥ 昨日的 3 倍
3. 新信号首次出现 — 过去 7 天从未出现，今天突然被报道
"""
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

logger = logging.getLogger(__name__)

def _resolve_digest_dir() -> Path:
    override = os.getenv("NEWS_DIGEST_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent.parent / "data" / "digests"


DIGEST_DIR = _resolve_digest_dir()

# 保留最近 14 天的 digest
MAX_DIGEST_DAYS = 14


def extract_entities(news_list: List[Dict[str, Any]], top_k: int = 30) -> Dict[str, int]:
    """从新闻列表中提取关键实体及其出现频次"""
    entity_counts = defaultdict(int)
    
    for item in news_list:
        title = item.get('title', '')
        summary = item.get('summary', '')
        text = f"{title} {summary}"
        
        if JIEBA_AVAILABLE:
            keywords = jieba.analyse.extract_tags(text, topK=10, withWeight=True)
            for kw, weight in keywords:
                # 过滤太短或太通用的词
                if len(kw) >= 2 and kw not in _STOPWORDS:
                    entity_counts[kw] += 1
        else:
            # 简单回退：用标题前10字作为标识
            if len(title) >= 4:
                entity_counts[title[:10]] += 1
    
    # 返回 top_k
    sorted_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_entities[:top_k])


# 常见停用词
_STOPWORDS = {
    '的', '了', '是', '在', '和', '与', '或', '等', '被', '对', '为', '有', '也',
    '将', '会', '到', '说', '这', '那', '个', '中', '上', '下', '大', '后', '要',
    '年', '月', '日', '时', '分', '而', '并', '及', '以', '其', '于', '由', '从',
    'the', 'a', 'an', 'in', 'of', 'to', 'and', 'or', 'is', 'it', 'for', 'with',
    '报告', '公司', '行业', '数据', '显示', '表示', '据悉', '据悉', '据', '称',
    # 技术噪音词
    'https', 'http', 'URL', 'Comments', 'www', 'com', 'html', 'json', 'xml',
    '2026', '2025', '2024',  # 年份太通用
    # 常见英文噪音
    'will', 'its', '...', 'the', 'new', 'that', 'this', 'from', 'has', 'have',
    'more', 'been', 'was', 'were', 'are', 'but', 'not', 'all', 'their', 'has',
}


def save_daily_digest(date: str, entities: Dict[str, int], total_news: int, 
                       cluster_count: int, top_event: str = '') -> str:
    """保存当日 digest 到文件"""
    digest = {
        'date': date,
        'total_news': total_news,
        'cluster_count': cluster_count,
        'top_event': top_event,
        'entities': entities,
        'generated_at': datetime.now().isoformat(),
    }
    
    filepath = DIGEST_DIR / f"digest_{date}.json"
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("Failed to save digest to %s: %s", filepath, exc)
        return ""
    
    # 清理过期 digest
    _cleanup_old_digests()
    
    logger.info(f"Digest saved for {date}: {len(entities)} entities")
    return str(filepath)


def _cleanup_old_digests():
    """删除超过 MAX_DIGEST_DAYS 天的 digest 文件"""
    if not DIGEST_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=MAX_DIGEST_DAYS)
    for f in DIGEST_DIR.glob("digest_*.json"):
        try:
            with open(f, 'r') as fh:
                d = json.load(fh)
            digest_date = datetime.strptime(d['date'], '%Y-%m-%d')
            if digest_date < cutoff:
                f.unlink()
        except (json.JSONDecodeError, KeyError, ValueError):
            f.unlink()


def load_digests(days: int = 7) -> List[Dict[str, Any]]:
    """加载过去 N 天的 digest"""
    digests = []
    if not DIGEST_DIR.exists():
        return digests
    for i in range(1, days + 1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        filepath = DIGEST_DIR / f"digest_{date}.json"
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    digests.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue
    return digests


def detect_trends(today_entities: Dict[str, int], 
                  past_digests: List[Dict[str, Any]],
                  today_date: str = '') -> Dict[str, List[Dict]]:
    """
    检测趋势信号
    
    返回:
    {
        'continuous': [...],      # 连续报道
        'surge': [...],           # 热度骤升
        'first_seen': [...],      # 新信号
    }
    """
    results = {
        'continuous': [],
        'surge': [],
        'first_seen': [],
    }
    
    if not past_digests:
        return results
    
    # 构建历史实体追踪
    history: Dict[str, List[int]] = defaultdict(list)  # entity -> [count_per_day]
    
    for digest in past_digests:
        entities = digest.get('entities', {})
        all_known = set(history.keys()) | set(entities.keys())
        for entity in all_known:
            history[entity].append(entities.get(entity, 0))
    
    # 加入今日数据
    for entity in set(list(history.keys()) + list(today_entities.keys())):
        history[entity].append(today_entities.get(entity, 0))
    
    today_idx = len(past_digests)  # 今日在 history 中的索引
    
    # 1. 连续报道：过去 N 天中至少出现了 N-1 天（至少 1 天时出现即算连续）
    total_past_days = len(past_digests)
    min_continuous_days = max(1, total_past_days // 2) if total_past_days > 0 else 1
    for entity, counts in history.items():
        if entity not in today_entities:
            continue
        
        # 计算出现天数（不含今天）
        past_days_present = sum(1 for c in counts[:-1] if c > 0)
        if past_days_present >= min_continuous_days:
            today_count = counts[-1]
            results['continuous'].append({
                'entity': entity,
                'days_present': past_days_present,
                'today_count': today_count,
                'trend': '持续升温' if counts[-1] > counts[-2] else '持续关注',
            })
    
    # 2. 热度骤升：今日报道量 ≥ 昨日的 3 倍（昨日 > 0）
    for entity in today_entities:
        if entity not in history or len(history[entity]) < 2:
            continue
        
        yesterday_count = history[entity][-2]
        today_count = history[entity][-1]
        
        if yesterday_count > 0 and today_count >= yesterday_count * 3:
            results['surge'].append({
                'entity': entity,
                'yesterday_count': yesterday_count,
                'today_count': today_count,
                'ratio': f"{today_count / max(yesterday_count, 1):.1f}x",
            })
    
    # 3. 新信号首次出现：过去所有天都是 0，今天 > 0
    all_past_entities = set()
    for digest in past_digests:
        all_past_entities.update(digest.get('entities', {}).keys())
    
    for entity in today_entities:
        if entity not in all_past_entities and today_entities[entity] > 0:
            results['first_seen'].append({
                'entity': entity,
                'today_count': today_entities[entity],
            })
    
    # 排序
    results['continuous'].sort(key=lambda x: x['today_count'], reverse=True)
    results['surge'].sort(key=lambda x: int(x['ratio'].replace('x', '')), reverse=True)
    results['first_seen'].sort(key=lambda x: x['today_count'], reverse=True)
    
    return results


def generate_trend_report(trends: Dict[str, List[Dict]]) -> str:
    """生成趋势信号 Markdown 报告"""
    md = []
    has_signals = False
    
    # 连续报道
    if trends['continuous']:
        has_signals = True
        md.append("\n## 📈 连续报道追踪\n")
        md.append("> 以下实体被连续多日报道，值得持续关注\n")
        for item in trends['continuous'][:5]:
            md.append(f"- **{item['entity']}** — 连续 {item['days_present']} 天 | 今日 {item['today_count']} 条 | 趋势: {item['trend']}")
        md.append("")
    
    # 热度骤升
    if trends['surge']:
        has_signals = True
        md.append("\n## 🚀 热度骤升\n")
        md.append("> 以下实体今日报道量突然飙升\n")
        for item in trends['surge'][:5]:
            md.append(f"- **{item['entity']}** — 昨日 {item['yesterday_count']} 条 → 今日 {item['today_count']} 条（{item['ratio']}倍）⚠️")
        md.append("")
    
    # 新信号
    if trends['first_seen']:
        has_signals = True
        md.append("\n## 🔔 新信号首次出现\n")
        md.append("> 以下实体在过去一周首次被报道\n")
        for item in trends['first_seen'][:5]:
            md.append(f"- **{item['entity']}** — 今日 {item['today_count']} 条报道")
        md.append("")
    
    if not has_signals:
        md.append("\n## 📈 趋势信号\n")
        md.append("> 暂无趋势信号（需要积累 2 天以上的历史数据）\n")
    
    return '\n'.join(md)
