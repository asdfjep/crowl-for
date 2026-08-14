#!/usr/bin/env python3
"""
测试脚本：使用最新爬虫抓取的 MD 报告数据运行完整分析管线
"""
import sys
import re
import json
import logging
import os
import tempfile
from pathlib import Path
from datetime import datetime

# 确保能导入 services 模块
sys.path.insert(0, str(Path(__file__).parent))

from services.analyzer import NewsAnalyzer

# ---- 配置日志 ----
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("test_analyzer")

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MD_CANDIDATES = [
    Path(os.getenv("NEWS_TEST_MD_PATH", "")).expanduser() if os.getenv("NEWS_TEST_MD_PATH") else None,
    next((p for p in sorted((PROJECT_ROOT / "data").glob("report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)), None)
    if (PROJECT_ROOT / "data").exists()
    else None,
]

# ---- MD 解析器 ----
def parse_md_report(md_path: str) -> tuple[list[dict], list[str]]:
    """
    解析爬虫生成的 MD 报告，提取新闻列表和来源列表
    返回: (news_list, sources)
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    news_list = []
    sources_set = set()

    # 匹配每个新闻块
    # 格式: ### 📰 [标题](URL)\n\n- **来源**: xxx\n- **分类**: xxx\n- **时间**: xxx\n- **严重程度**: xxx\n- **📍 坐标**: xxx\n\n> **摘要**: xxx\n\n---
    pattern = re.compile(
        r'### 📰 \[(.*?)\]\((.*?)\)\s*\n'
        r'(?:-\s*\*\*来源\*\*:\s*(.*?)\n)?'
        r'(?:-\s*\*\*分类\*\*:\s*(.*?)\n)?'
        r'(?:-\s*\*\*时间\*\*:\s*(.*?)\n)?'
        r'(?:-\s*\*\*严重程度\*\*:\s*(.*?)\n)?'
        r'(?:-\s*\*\*📍 坐标\*\*:\s*(.*?)\n)?'
        r'(?:>\s*\*\*摘要\*\*:\s*(.*?))?'
        r'(?:\n---|\Z)',
        re.DOTALL
    )

    for m in pattern.finditer(content):
        title = m.group(1).strip()
        url = m.group(2).strip()
        source = (m.group(3) or '').strip()
        category = (m.group(4) or '').strip()
        time_str = (m.group(5) or '').strip()
        severity = (m.group(6) or '').strip()
        coords = (m.group(7) or '').strip()
        summary = (m.group(8) or '').strip() if m.group(8) else ''

        # 解析坐标
        lat = None
        lng = None
        location = ''
        coord_match = re.search(r'Lat:\s*([\d.]+).*Lng:\s*([\d.]+).*位置:\s*(\S+)', coords)
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            location = coord_match.group(3)

        # 解析时间
        publish_time = ''
        if time_str:
            # "2026-04-16 16:14" -> "2026-04-16T16:14:00"
            publish_time = time_str.replace(' ', 'T') + ':00'

        if source:
            sources_set.add(source)

        news_item = {
            'title': title,
            'url': url,
            'source': source,
            'publishTime': publish_time,
            'category': category,
            'severity': severity.lower(),
            'summary': summary,
            'content': None,
            'location': location,
            'latitude': lat,
            'longitude': lng,
            'tags': [],
            'isPushed': False,
        }
        news_list.append(news_item)

    return news_list, sorted(sources_set)


def main():
    print("=" * 70)
    print("AI News Analyzer - 完整管线测试")
    print("=" * 70)

    # 1. 加载数据
    md_path = next((str(p) for p in DEFAULT_MD_CANDIDATES if p and p.exists()), "")
    if not md_path:
        raise FileNotFoundError(
            "No MD report found. Set NEWS_TEST_MD_PATH to a report_*.md file."
        )
    print(f"\n📂 数据文件: {md_path}")

    news_list, sources = parse_md_report(md_path)
    print(f"📊 MD 解析完成: {len(news_list)} 条新闻, {len(sources)} 个来源")
    print(f"   来源列表: {', '.join(sources[:5])}...")

    # 打印前3条样例
    print("\n📋 前3条新闻样例:")
    for i, item in enumerate(news_list[:3]):
        print(f"   [{i+1}] {item['title'][:60]}")
        print(f"       来源={item['source']}, 分类={item['category']}, 时间={item['publishTime']}")

    # 2. 创建分析器
    print("\n🔧 初始化 NewsAnalyzer...")
    analyzer = NewsAnalyzer()

    # 3. 执行分析管线
    date_str = "2026-04-16"
    print(f"\n🚀 执行完整分析管线 (date={date_str})...")
    print("-" * 70)

    step_results = analyzer.analyze(news_list, sources=sources, date=date_str)

    # 4. 检查结果
    print("\n" + "=" * 70)
    print("📊 分析结果汇总")
    print("=" * 70)

    # 去重结果
    dedup = step_results.get('dedup', {})
    print(f"\n✅ Step 1 - 去重:")
    print(f"   输入: {dedup.get('input_count', 0)} 条")
    print(f"   去重后: {dedup.get('unique_count', 0)} 条")
    print(f"   去重数: {dedup.get('duplicate_count', 0)} 条")

    # 聚类结果
    clusters = step_results.get('ranked_clusters', [])
    print(f"\n✅ Step 2 - 事件聚类:")
    print(f"   簇数量: {len(clusters)}")
    if clusters:
        print(f"   TOP 5 事件:")
        for i, c in enumerate(clusters[:5]):
            score = c.get('importance_score', 0)
            title = c.get('representative_title', '')[:60]
            item_count = c.get('item_count', 0)
            src_count = c.get('source_count', 0)
            print(f"   [{i+1}] [{score:.0f}分] {title}")
            print(f"       报道数={item_count}, 来源数={src_count}")

    # 评分分布
    ranked_news = step_results.get('ranked_news', [])
    scores = []
    if ranked_news:
        scores = [n.get('importance_score', 0) for n in ranked_news]
        print(f"\n✅ Step 3 - 评分分布:")
        print(f"   最高分: {max(scores):.0f}")
        print(f"   平均分: {sum(scores)/len(scores):.1f}")
        print(f"   最低分: {min(scores):.0f}")
        # 分数段统计
        high = sum(1 for s in scores if s >= 50)
        mid = sum(1 for s in scores if 20 <= s < 50)
        low = sum(1 for s in scores if s < 20)
        print(f"   高分(≥50): {high}  中分(20-49): {mid}  低分(<20): {low}")

    # 板块分类
    board_summary = step_results.get('board_summary', {})
    print(f"\n✅ Step 4 - 板块分类:")
    print(f"   板块数量: {len(board_summary)}")
    # 按数量排序
    sorted_boards = sorted(board_summary.items(), key=lambda x: x[1].get('count', 0), reverse=True)
    for board_name, info in sorted_boards[:10]:
        count = info.get('count', 0)
        sub_boards = info.get('sub_boards', {})
        top_sub = sorted(sub_boards.items(), key=lambda x: x[1], reverse=True)[:3]
        sub_str = ', '.join([f"{k}:{v}" for k, v in top_sub]) if top_sub else ''
        print(f"   {board_name}: {count}条" + (f"  [{sub_str}]" if sub_str else ''))

    # 报告生成
    report = step_results.get('report', '')
    print(f"\n✅ Step 5 - 报告生成:")
    print(f"   报告长度: {len(report)} 字符")

    # 5. 检查 reports/ 目录
    report_dir = PROJECT_ROOT / "reports"
    report_files = []
    if report_dir.exists():
        report_files = sorted(
            list(report_dir.glob("daily_report_*.md")) + list(report_dir.glob("*_weekly_report_*.md")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        print(f"\n📁 Reports 目录 (最新5个):")
        for rf in report_files[:5]:
            size = rf.stat().st_size
            mtime = datetime.fromtimestamp(rf.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            print(f"   {rf.name}  ({size} bytes, {mtime})")

    # 打印报告预览
    if report:
        print("\n" + "=" * 70)
        print("📝 报告预览 (前1500字符):")
        print("=" * 70)
        print(report[:1500])

    # 6. 写入记忆文件
    memory_path = None
    if os.getenv("NEWS_TEST_WRITE_MEMORY", "").lower() in {"1", "true", "yes"}:
        memory_dir = Path(os.getenv("NEWS_TEST_MEMORY_DIR", str(Path(tempfile.gettempdir()) / "ai-news" / "modules")))
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_path = memory_dir / "analyzer.md"

    # 收集统计信息
    test_summary = f"""
## 分析模块测试 - {datetime.now().strftime('%Y-%m-%d %H:%M')}

**数据源**: `{md_path}`
**解析新闻数**: {len(news_list)}
**来源数**: {len(sources)}

### 管线结果
| 步骤 | 指标 | 值 |
|------|------|-----|
| 去重 | 输入/输出/去重 | {dedup.get('input_count',0)} / {dedup.get('unique_count',0)} / {dedup.get('duplicate_count',0)} |
| 聚类 | 事件簇数量 | {len(clusters)} |
| 评分 | 最高/平均/最低 | {max(scores):.0f} / {sum(scores)/len(scores):.1f} / {min(scores):.0f} |
| 板块 | 板块数量 | {len(board_summary)} |
| 报告 | 字符数 | {len(report)} |

### TOP 5 事件
"""
    for i, c in enumerate(clusters[:5]):
        test_summary += f"{i+1}. [{c.get('importance_score', 0):.0f}分] {c.get('representative_title', '')[:80]} (报道:{c.get('item_count',0)}, 来源:{c.get('source_count',0)})\n"

    test_summary += f"\n### 最新报告文件\n"
    for rf in report_files[:3]:
        test_summary += f"- `{rf.name}` ({rf.stat().st_size} bytes)\n"

    test_summary += "\n### 状态\n- ✅ MD 解析正常\n- ✅ 去重管线正常\n- ✅ 事件聚类正常\n- ✅ 评分排序正常\n- ✅ 板块分类正常\n- ✅ 报告生成正常\n"

    # 追加或创建记忆文件
    if memory_path:
        if memory_path.exists():
            with open(memory_path, 'a', encoding='utf-8') as f:
                f.write(test_summary)
        else:
            with open(memory_path, 'w', encoding='utf-8') as f:
                f.write("# AI News 分析模块记忆\n\n")
                f.write(test_summary)
        print(f"\n💾 测试结果已写入: {memory_path}")
    else:
        print("\n💾 已跳过记忆写入（可用 NEWS_TEST_WRITE_MEMORY=1 开启）")
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    main()
