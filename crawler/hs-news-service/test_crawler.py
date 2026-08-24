#!/usr/bin/env python3.12
"""
HS News Crawler - Test Script
Runs a single crawl cycle and reports results.
"""
import asyncio
import sys
import os
import json
import traceback
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.scheduler import Scheduler

async def main():
    results = {
        "status": "unknown",
        "timestamp": datetime.now().isoformat(),
        "total_news": 0,
        "sources_total": 0,
        "sources_success": 0,
        "sources_failed": 0,
        "errors": [],
        "data_files": []
    }

    print("=" * 60)
    print("HS News Crawler - Test Run")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # 1. Initialize Scheduler
        print("\n[1] Initializing Scheduler...")
        scheduler = Scheduler()

        # 2. Load sources
        print("[2] Loading sources...")
        await scheduler.load_sources()
        results["sources_total"] = len(scheduler.sources)
        print(f"    Loaded {len(scheduler.sources)} sources")

        # 3. Run crawl
        print("\n[3] Starting crawl cycle...")
        print("-" * 60)

        news = await scheduler.fetch_all_news()

        results["total_news"] = len(news)
        print("-" * 60)
        print(f"\n[4] Crawl complete. Total news items: {len(news)}")

        # 4. Save results
        print("[5] Saving results...")
        scheduler.save_news(news)

        results["status"] = "success"

    except Exception as e:
        results["status"] = "failed"
        results["errors"].append(str(e))
        results["errors"].append(traceback.format_exc())
        print(f"\n[ERROR] Crawl failed: {e}")
        print(traceback.format_exc())

    # 5. Check data directory
    print("\n[6] Checking data directory...")
    data_dir = Path("/mnt/d/GitHub/hs-news-service/data")
    if data_dir.exists():
        json_files = sorted(data_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        md_files = sorted(data_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        print(f"    Latest JSON files:")
        for f in json_files[:5]:
            size_kb = f.stat().st_size / 1024
            results["data_files"].append(f.name)
            print(f"      - {f.name} ({size_kb:.1f} KB)")
        
        if md_files:
            print(f"    Latest MD report: {md_files[0].name}")

    # Summary
    print("\n" + "=" * 60)
    print(f"STATUS: {results['status'].upper()}")
    print(f"Total news: {results['total_news']}")
    print(f"Sources: {results['sources_total']}")
    if results['errors']:
        print(f"Errors: {len(results['errors'])}")
        for err in results['errors'][:3]:
            print(f"  - {err[:100]}")
    print("=" * 60)

    # Write results summary
    output = json.dumps(results, indent=2, ensure_ascii=False)
    print(f"\nTest results JSON:\n{output}")

    return results

if __name__ == "__main__":
    asyncio.run(main())
