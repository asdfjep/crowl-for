"""
业务关联标记模块
根据配置的关键词为新闻打上业务关联标签：
⚡ 高度关注 — 直接相关业务（偏光片、光电等）
📌 值得关注 — 行业相关（AI、半导体、新能源等）
📊 宏观参考 — 宏观环境（政策、汇率、经济等）
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# 业务关注关键词配置
# 按优先级分级：高/中/低
# 用户可根据实际业务调整
# ============================================================
BUSINESS_KEYWORDS = {
    'high': {
        'label': '⚡ 高度关注',
        'description': '直接相关：偏光片、光电核心业务',
        'keywords': [
            # 偏光片/显示核心
            '偏光片', 'polarizer', 'POL', '光学膜', '相位差膜', '补偿膜',
            '光电', '光电材料', '光学材料',
            'LCD', 'OLED', 'Mini-LED', 'Micro-LED',
            '面板', '显示面板', '液晶面板', '柔性显示',
            '京东方', 'BOE', '华星光电', 'CSOT', 'TCL华星',
            'LG Display', 'LGD', '三星显示', 'Samsung Display',
            '友达光电', 'AUO', '群创光电', 'Innolux',
            '深天马', '天马微电子', '信利', '维信诺',
            '杉杉', '杉杉股份', '杉杉光电', '盛波光电',
            '三利谱', '恒美光电', '住友化学', '日东电工',
            '明基材料', '诚美材', 'LG化学',
            '偏光片产线', '偏光片产能', 'OLED产线',
        ],
    },
    'medium': {
        'label': '📌 值得关注',
        'description': '行业相关：上下游产业链、技术趋势',
        'keywords': [
            # 上游材料/设备
            '半导体', '芯片', '晶圆', '硅片', '光刻胶',
            '电子化学品', '靶材', '蚀刻液', '清洗液',
            'LED芯片', '驱动IC', '背光模组',
            # 下游应用
            '智能手机', '平板电脑', '电视', '显示器',
            '车载显示', '车载屏幕', '智能汽车',
            'VR', 'AR', '虚拟现实', '增强现实', 'MR',
            '可穿戴', '智能手表', '折叠屏', '卷曲屏',
            # 技术趋势
            'AI', '人工智能', '机器学习', '大模型',
            '自动化', '智能制造', '工业4.0',
            '新能源', '电池', '储能', '光伏',
            '5G', '6G', '物联网', 'IoT',
            # 行业事件
            '并购', '收购', '投资', '扩产', '投产',
            '财报', '营收', '利润', '订单',
        ],
    },
    'low': {
        'label': '📊 宏观参考',
        'description': '宏观环境：政策、经济、汇率等',
        'keywords': [
            # 宏观经济
            'GDP', 'CPI', 'PPI', 'PMI',
            '利率', '加息', '降息', '通胀',
            '汇率', '人民币', '美元', '日元', '韩元',
            '贸易', '关税', '制裁', '出口', '进口',
            # 政策法规
            '发改委', '工信部', '商务部', '财政部',
            '十四五', '十五五', '规划', '政策',
            '补贴', '税收', '优惠', '扶持',
            # 地缘政治
            '中美', '中日', '中韩', '贸易摩擦',
            '供应链', '产业链', '脱钩', '国产替代',
            # 社会事件
            '地震', '台风', '灾害', '疫情',
        ],
    },
}


def classify_relevance(title: str, summary: str = '') -> Optional[Dict[str, str]]:
    """
    判断新闻的业务关联级别
    
    返回: {'level': 'high/medium/low', 'label': '⚡ 高度关注', 'matched_keywords': ['偏光片', 'OLED']}
          或 None（无匹配）
    """
    import re
    text = f"{title} {summary}"
    text_lower = text.lower()
    
    # 按优先级从高到低匹配
    for level in ['high', 'medium', 'low']:
        config = BUSINESS_KEYWORDS[level]
        matched = []
        for kw in config['keywords']:
            kw_lower = kw.lower()
            # 英文关键词使用单词边界匹配，中文直接子串匹配
            if any('\u4e00' <= c <= '\u9fff' for c in kw):
                # 中文：直接子串匹配
                if kw_lower in text_lower:
                    matched.append(kw)
            else:
                # 英文：单词边界匹配，避免 POL 匹配到 polygons
                if re.search(r'\b' + re.escape(kw_lower) + r'\b', text_lower):
                    matched.append(kw)
        
        if matched:
            return {
                'level': level,
                'label': config['label'],
                'matched_keywords': matched[:5],  # 最多返回5个匹配词
            }
    
    return None


def tag_news_list(news_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    为新闻列表批量打业务关联标签
    
    返回: 各级别数量统计 {'high': 12, 'medium': 45, 'low': 89, 'none': 138}
    """
    stats = {'high': 0, 'medium': 0, 'low': 0, 'none': 0}
    
    for item in news_list:
        title = item.get('title', '')
        summary = item.get('summary', '')
        
        result = classify_relevance(title, summary)
        if result:
            item['business_relevance'] = result
            stats[result['level']] += 1
        else:
            stats['none'] += 1
    
    return stats


def generate_relevance_section(news_list: List[Dict[str, Any]]) -> str:
    """生成业务关联标记的 Markdown 段落"""
    md = ["\n## 🔗 业务关联标记\n"]
    
    high_news = [n for n in news_list if n.get('business_relevance', {}).get('level') == 'high']
    medium_news = [n for n in news_list if n.get('business_relevance', {}).get('level') == 'medium']
    low_news = [n for n in news_list if n.get('business_relevance', {}).get('level') == 'low']
    
    # 高优先级（详细列出）
    md.append(f"\n### ⚡ 高度关注（{len(high_news)} 条）\n")
    if high_news:
        md.append("> 直接相关业务：偏光片、光电核心业务\n")
        md.append("| 排名 | 新闻标题 | 匹配词 | 评分 | 来源 |")
        md.append("|------|----------|--------|------|------|")
        for i, item in enumerate(high_news[:15], 1):
            title = item.get('title', '')[:45]
            url = item.get('url', '#')
            score = item.get('importance_score', 0)
            source = item.get('source', '')
            rel = item.get('business_relevance', {})
            keywords = ', '.join(rel.get('matched_keywords', [])[:3])
            md.append(f"| {i} | [{title}]({url}) | {keywords} | {score:.0f} | {source} |")
        if len(high_news) > 15:
            md.append(f"\n> ... 还有 {len(high_news) - 15} 条")
    else:
        md.append("> 今日无直接相关报道\n")
    
    # 中优先级（列表形式）
    md.append(f"\n### 📌 值得关注（{len(medium_news)} 条）\n")
    if medium_news:
        md.append("> 行业相关：上下游产业链、技术趋势\n")
        md.append("| 排名 | 新闻标题 | 匹配词 | 评分 |")
        md.append("|------|----------|--------|------|")
        for i, item in enumerate(medium_news[:10], 1):
            title = item.get('title', '')[:45]
            url = item.get('url', '#')
            score = item.get('importance_score', 0)
            rel = item.get('business_relevance', {})
            keywords = ', '.join(rel.get('matched_keywords', [])[:2])
            md.append(f"| {i} | [{title}]({url}) | {keywords} | {score:.0f} |")
        if len(medium_news) > 10:
            md.append(f"\n> ... 还有 {len(medium_news) - 10} 条")
    else:
        md.append("> 今日无值得关注的相关报道\n")
    
    # 低优先级（仅统计）
    md.append(f"\n### 📊 宏观参考（{len(low_news)} 条）\n")
    if low_news:
        md.append("> 宏观环境：政策、经济、汇率等\n")
        # 只列统计
        categories = set()
        sources = set()
        for item in low_news:
            categories.add(item.get('category', ''))
            sources.add(item.get('source', ''))
        md.append(f"> 覆盖类别: {', '.join(c for c in categories if c)} | 来源: {len(sources)} 个\n")
    else:
        md.append("> 今日无宏观相关报道\n")
    
    md.append("")
    return '\n'.join(md)
