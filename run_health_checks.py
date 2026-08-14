#!/usr/bin/env python3
"""Run source health checks for one or more configured topics.

This is a standalone wrapper around:

    python run.py --topic <topic> --health-check

It does not generate weekly reports and does not repair code. It only runs the
health checks, prints a concise summary, and writes an aggregate markdown file.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_DIR / "reports"
LOGS_DIR = PROJECT_DIR / "logs"
DEFAULT_TOPICS = ["ai", "commercial_space", "display_polarizer"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenClaw source health checks.")
    parser.add_argument(
        "--topics",
        nargs="+",
        default=DEFAULT_TOPICS,
        help="Topics to check. Default: ai commercial_space display_polarizer",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Timeout in seconds for each topic health check. Default: 900",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if one topic health check fails.",
    )
    return parser.parse_args()


def extract_line(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def run_topic(topic: str, timeout: int) -> dict:
    started = datetime.now()
    cmd = [sys.executable, "run.py", "--topic", topic, "--health-check"]
    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return {
        "topic": topic,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "started": started,
        "finished": datetime.now(),
        "report": extract_line(r"^Report:\s*(.+)$", output),
        "json": extract_line(r"^JSON:\s*(.+)$", output),
        "summary": extract_line(r"^Summary:\s*(.+)$", output),
        "output": output,
    }


def render_summary(results: Iterable[dict]) -> str:
    lines = [
        "# OpenClaw 数据源巡检汇总",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 项目目录：{PROJECT_DIR}",
        "",
        "| Topic | 状态 | Summary | Markdown | JSON |",
        "|---|---:|---|---|---|",
    ]
    for item in results:
        status = "ok" if item["ok"] else f"error({item['returncode']})"
        report = item["report"] or "-"
        json_path = item["json"] or "-"
        summary = item["summary"] or "-"
        lines.append(
            f"| {item['topic']} | {status} | {summary} | {report} | {json_path} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for topic in args.topics:
        print(f"\n=== health-check:{topic} ===", flush=True)
        try:
            result = run_topic(topic, args.timeout)
        except subprocess.TimeoutExpired as exc:
            result = {
                "topic": topic,
                "ok": False,
                "returncode": -1,
                "started": datetime.now(),
                "finished": datetime.now(),
                "report": "",
                "json": "",
                "summary": f"timeout after {args.timeout}s",
                "output": str(exc),
            }
        results.append(result)
        print(result["summary"] or ("ok" if result["ok"] else "failed"), flush=True)
        if result["report"]:
            print(f"Report: {result['report']}", flush=True)
        if not result["ok"]:
            print(result["output"][-3000:], flush=True)
            if args.stop_on_error:
                break

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = LOGS_DIR / f"source_health_all_{stamp}.md"
    summary_path.write_text(render_summary(results), encoding="utf-8")
    print(f"\nAggregate summary: {summary_path}")

    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
