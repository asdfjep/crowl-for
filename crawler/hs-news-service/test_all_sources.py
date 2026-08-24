#!/usr/bin/env python3
"""逐个测试所有信息源，报告每个源的抓取结果"""
import asyncio
import sys
import os
import json
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources.base import NewsItem

# 普通爬虫
from sources.thsnews import ThsnewsCrawler
from sources.aerospace import AerospaceCrawler
from sources.ai_news import AINewsCrawler
from sources.polarizer import PolarizerCrawler
from sources.conflict_events import ConflictEventsCrawler
from sources.financial_markets import FinancialMarketsCrawler
from sources.enhanced import CLSCrawler, DisplayDailyCrawler, SpaceChinaCrawler
from sources.space_com import SpaceComCrawler
from sources.nasa import NASACrawler
from sources.the_decoder import TheDecoderCrawler
from sources.synced import SyncedCrawler
from sources.deepmind import DeepMindCrawler
from sources.venturebeat import VentureBeatCrawler
from sources.eu_ai import EUAICrawler
from sources.leiphone import LeiphoneCrawler
from sources.qbitai import QbitaiCrawler
from sources.aibusiness import AIBusinessCrawler
from sources.lgdisplay import LGDisplayCrawler

# Playwright 爬虫
from sources.ofweek_pw import OFweekCrawler
from sources.kr36_pw import Kr36Crawler
from sources.boe_pw import BOECrawler
from sources.spacenews_pw import SpaceNewsCrawler

ALL_SOURCES = [
    # 普通爬虫 (HTTP)
    ("thsnews", ThsnewsCrawler),
    ("aerospace", AerospaceCrawler),
    ("ai_news", AINewsCrawler),
    ("polarizer", PolarizerCrawler),
    ("conflict_events", ConflictEventsCrawler),
    ("financial_markets", FinancialMarketsCrawler),
    ("cls", CLSCrawler),
    ("displaydaily", DisplayDailyCrawler),
    ("spacechina", SpaceChinaCrawler),
    ("space_com", SpaceComCrawler),
    ("nasa", NASACrawler),
    ("the_decoder", TheDecoderCrawler),
    ("synced", SyncedCrawler),
    ("deepmind", DeepMindCrawler),
    ("venturebeat", VentureBeatCrawler),
    ("eu_ai", EUAICrawler),
    ("leiphone", LeiphoneCrawler),
    ("qbitai", QbitaiCrawler),
    ("aibusiness", AIBusinessCrawler),
    ("lgdisplay", LGDisplayCrawler),
    # Playwright 爬虫
    ("ofweek", OFweekCrawler),
    ("36kr", Kr36Crawler),
    ("boe", BOECrawler),
    ("spacenews", SpaceNewsCrawler),
]

async def test_source(name, crawler_cls):
    """测试单个信息源"""
    import time
    start = time.time()
    try:
        crawler = crawler_cls()
        async with crawler:
            news = await asyncio.wait_for(crawler.fetch_news(), timeout=30)
        duration = time.time() - start
        sample = ""
        if news:
            first = news[0]
            title = first.title if hasattr(first, 'title') else first.get('title', '')
            sample = title[:60]
        return {
            "name": name,
            "status": "OK",
            "count": len(news),
            "duration": f"{duration:.1f}s",
            "sample": sample,
            "error": None,
        }
    except asyncio.TimeoutError:
        duration = time.time() - start
        return {"name": name, "status": "TIMEOUT", "count": 0, "duration": f"{duration:.1f}s", "sample": "", "error": "Timeout (>30s)"}
    except Exception as e:
        duration = time.time() - start
        err = str(e)[:100]
        return {"name": name, "status": "FAILED", "count": 0, "duration": f"{duration:.1f}s", "sample": "", "error": err}

async def main():
    print("=" * 80)
    print("HS News Service - 全部信息源抓取测试")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"信息源总数: {len(ALL_SOURCES)}")
    print("=" * 80)
    
    results = []
    total_ok = 0
    total_fail = 0
    total_timeout = 0
    total_news = 0

    for i, (name, cls) in enumerate(ALL_SOURCES, 1):
        print(f"\n[{i}/{len(ALL_SOURCES)}] 测试: {name}...", end=" ", flush=True)
        result = await test_source(name, cls)
        results.append(result)
        total_news += result["count"]
        
        if result["status"] == "OK":
            total_ok += 1
            print(f"OK - {result['count']} 条新闻 ({result['duration']})")
            if result["sample"]:
                print(f"    示例: {result['sample']}")
        elif result["status"] == "TIMEOUT":
            total_timeout += 1
            print(f"TIMEOUT ({result['duration']})")
        else:
            total_fail += 1
            print(f"FAILED - {result['error']}")

    # 汇总报告
    print("\n" + "=" * 80)
    print("汇总报告")
    print("=" * 80)
    print(f"  ✅ 成功: {total_ok}")
    print(f"  ❌ 失败: {total_fail}")
    print(f"  ⏱️ 超时: {total_timeout}")
    print(f"  📰 总新闻数: {total_news}")
    print("=" * 80)
    
    # 按状态分组
    print("\n--- 成功的信息源 ---")
    for r in results:
        if r["status"] == "OK":
            print(f"  ✅ {r['name']:20s} → {r['count']:3d} 条 ({r['duration']})")
    
    if total_timeout:
        print("\n--- 超时的信息源 ---")
        for r in results:
            if r["status"] == "TIMEOUT":
                print(f"  ⏱️ {r['name']:20s} → 超时 ({r['duration']})")
    
    if total_fail:
        print("\n--- 失败的信息源 ---")
        for r in results:
            if r["status"] == "FAILED":
                print(f"  ❌ {r['name']:20s} → {r['error']}")
    
    # 保存结果
    output = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": len(results),
            "ok": total_ok,
            "failed": total_fail,
            "timeout": total_timeout,
            "total_news": total_news,
        },
        "results": results
    }
    
    out_path = os.path.join("data", f"test_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
