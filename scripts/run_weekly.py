#!/usr/bin/env python3
"""周一定时任务：抓取数据 → 批量巡检 → 批量分析（生成三份周报归为一组）。

在容器内执行（宿主机 cron 里调用）：
    docker exec -t news-analyzer python /app/scripts/run_weekly.py [YYYY-MM-DD]
"""
import os
import subprocess
import sys
from datetime import datetime

TOPICS = ["ai", "commercial_space", "display_polarizer"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /app
CRAWLER_DIR = "/app/crawler/hs-news-service"


def step(title: str) -> None:
    print(f"\n===== {title} =====", flush=True)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")

    step("1. 抓取数据（爬虫 run.py --once → 推送给分析服务落在 /app/data）")
    if os.path.isdir(CRAWLER_DIR):
        subprocess.run([sys.executable, "run.py", "--once"], cwd=CRAWLER_DIR, check=False)
    else:
        print("[跳过] 未找到爬虫目录", CRAWLER_DIR)

    from server_jobs import run_health_batch, run_analyze_batch

    step("2. 批量数据源巡检（三个主题一组）")
    try:
        health = run_health_batch({"topics": TOPICS})
        for topic, r in health["results"].items():
            print(f"- {topic}: {'正常' if r.get('ok') else '异常'}  {r.get('summary') or ''}")
    except Exception as exc:
        print(f"[巡检失败] {exc}")

    step("3. 批量运行分析（生成三份中文周报，共享时间戳归为一组）")
    try:
        results = run_analyze_batch({"topics": TOPICS, "use_llm": True, "date": date})
        for topic, r in results["results"].items():
            print(f"- {topic}: 事件簇={r['summary'].get('cluster_count')}  报告={r.get('report_name')}")
    except Exception as exc:
        print(f"[分析失败] {exc}")
        return 1

    print("\n完成：三份周报已在报告中心归为一批。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())