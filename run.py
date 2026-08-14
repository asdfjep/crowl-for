#!/usr/bin/env python3
"""
Shared News Analyzer entry point.

Usage:
  python run.py --topic ai
  python run.py --topic commercial_space
  python run.py --topic display_polarizer
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path


def _restart_with_bundled_python_if_available():
    """Use the bundled runtime so PDF/report dependencies match the interpreter."""
    if os.getenv("NEWS_SKIP_BUNDLED_PYTHON_REEXEC", "").lower() in {"1", "true", "yes"}:
        return

    bundled_python = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / "python.exe"
    )
    if not bundled_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    target_python = bundled_python.resolve()
    if current_python == target_python:
        return

    os.environ["NEWS_SKIP_BUNDLED_PYTHON_REEXEC"] = "1"
    os.execv(str(target_python), [str(target_python), *sys.argv])


_restart_with_bundled_python_if_available()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.analyzer import NewsAnalyzer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


WORKSPACE_ROOT = Path.home() / ".openclaw" / "workspace"
SERVICE_DIRS = {
    "ai": WORKSPACE_ROOT / ".tmp_ai_news_service" / "ai-news-service",
    "commercial_space": WORKSPACE_ROOT / ".tmp_commercial_space_news_service" / "commercial-space-news-service",
    "display_polarizer": WORKSPACE_ROOT / ".tmp_display_polarizer_news_service" / "display-polarizer-news-service",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run a configured weekly news analyzer")
    parser.add_argument(
        "--topic",
        default=os.getenv("NEWS_TOPIC", "ai"),
        help="Topic config name under configs/topics, e.g. ai, commercial_space, display_polarizer",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Optional explicit news_*.json file. Defaults to latest file from topic data_dir.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional report end date in YYYY-MM-DD. Defaults to current run date, not data crawlTime.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Run the matching crawler service once, export fresh JSON, then generate the report.",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check configured crawler sources and write a source health report.",
    )
    return parser.parse_args()


@lru_cache(maxsize=None)
def _python_is_usable(python_path: str) -> bool:
    try:
        completed = subprocess.run(
            [python_path, "-c", "import sys"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _service_python(service_dir: Path) -> str:
    venv_python = service_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists() and _python_is_usable(str(venv_python)):
        return str(venv_python)
    if venv_python.exists():
        logger.warning("Service venv python is not usable, falling back to current runtime: %s", venv_python)
    return sys.executable


def _extract_json_from_service_report(report_path: Path) -> list:
    content = report_path.read_text(encoding="utf-8")
    matches = re.findall(r"```json\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    for block in reversed(matches):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
    raise RuntimeError(f"No JSON news list found in service report: {report_path}")


def _latest_service_report(service_dir: Path, since: float = 0) -> Path:
    data_dir = service_dir / "data"
    reports = [
        path for path in data_dir.glob("report_*.md")
        if path.stat().st_mtime >= since
    ]
    if not reports:
        raise RuntimeError(f"Crawler did not produce a new report_*.md in {data_dir}")
    return max(reports, key=lambda path: path.stat().st_mtime)


def _write_analyzer_json(analyzer: NewsAnalyzer, news_items: list, sources: list) -> Path:
    analyzer.data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    output_path = analyzer.data_dir / f"news_{now.strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "crawlTime": now.isoformat(),
        "sources": sources,
        "news": news_items,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def refresh_topic_data(analyzer: NewsAnalyzer) -> str:
    service_dir = SERVICE_DIRS.get(analyzer.topic_key)
    if not service_dir or not service_dir.exists():
        raise RuntimeError(f"No crawler service configured for topic: {analyzer.topic_key}")

    logger.info("Refreshing data via crawler service: %s", service_dir)
    started_at = datetime.now().timestamp()
    cmd = [_service_python(service_dir), "run.py", "--once"]
    completed = subprocess.run(
        cmd,
        cwd=str(service_dir),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Crawler service failed with exit code {completed.returncode}: {' '.join(cmd)}")

    report_path = _latest_service_report(service_dir, since=started_at)
    news_items = _extract_json_from_service_report(report_path)
    sources = sorted({str(item.get("source", "")).strip() for item in news_items if item.get("source")})
    json_path = _write_analyzer_json(analyzer, news_items, sources)
    logger.info("Fresh crawler data exported: %s (%s news items)", json_path, len(news_items))
    return str(json_path)


def _extract_health_payload(output: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "results" in payload:
            return payload
    raise RuntimeError("Health check did not return a JSON payload")


def _issue_label(issue: str) -> str:
    labels = {
        "no_items": "没有抓到文章",
        "title_extract_abnormal": "标题提取异常",
        "title_too_short": "标题过短",
        "url_missing": "链接缺失",
        "time_extract_abnormal": "时间提取异常",
        "body_extract_abnormal": "正文/摘要提取异常",
        "fetch_failed": "访问或抓取失败",
    }
    if issue.startswith("stale_"):
        return f"连续 {issue.removeprefix('stale_').removesuffix('d')} 天左右无新内容"
    return labels.get(issue, issue)


def _format_health_markdown(analyzer: NewsAnalyzer, payload: dict) -> str:
    results = payload.get("results", [])
    summary = payload.get("summary", {})
    settings = payload.get("settings", {})
    checked_at = payload.get("checked_at", datetime.now().isoformat(timespec="seconds"))

    lines = [
        f"# {analyzer.topic_label}数据源巡检报告",
        "",
        f"- 巡检时间：{checked_at}",
        f"- 服务目录：{payload.get('service_dir', '')}",
        f"- 配置：单源超时 {settings.get('timeout_sec', '')} 秒，失败重试 {settings.get('retries', '')} 次，连续 {settings.get('stale_days', '')} 天无新内容标记为异常",
        f"- 结果：正常 {summary.get('ok', 0)} 个，重试恢复 {summary.get('recovered', 0) + summary.get('recovered_warn', 0)} 个，警告 {summary.get('warn', 0)} 个，失败 {summary.get('error', 0)} 个",
        "",
        "## 异常与需关注来源",
        "",
    ]

    problematic = [item for item in results if item.get("status") != "ok"]
    if not problematic:
        lines.append("暂无异常来源。")
    else:
        for item in problematic:
            issues = "、".join(_issue_label(issue) for issue in item.get("issues", [])) or "未标明"
            lines.extend([
                f"### {item.get('source', '')}",
                f"- 状态：{item.get('status', '')}",
                f"- 抓取数量：{item.get('items', 0)}",
                f"- 最新时间：{item.get('newest') or '未识别'}",
                f"- 问题：{issues}",
                f"- 重试次数：{item.get('attempts', 1)}",
                f"- 错误：{item.get('error') or '无'}",
                "",
            ])

    lines.extend([
        "## 全量巡检明细",
        "",
        "| 来源 | 状态 | 数量 | 最新时间 | 问题 | 耗时 |",
        "|---|---:|---:|---|---|---:|",
    ])
    for item in results:
        issues = "、".join(_issue_label(issue) for issue in item.get("issues", [])) or "-"
        lines.append(
            f"| {item.get('source', '')} | {item.get('status', '')} | {item.get('items', 0)} | "
            f"{item.get('newest') or '-'} | {issues} | {item.get('duration_sec', 0)}s |"
        )

    lines.extend([
        "",
        "## 自动恢复策略",
        "",
        "- 单个来源失败会按配置自动重试，重试成功会标为 `recovered`。",
        "- 抓到 0 篇、正文异常、时间异常、连续多天无新内容会标为 `warn`，不会静默混进周报。",
        "- 真正需要改选择器、绕反爬或新增备用源的情况，会留在本报告里，方便后续定点修复。",
    ])
    return "\n".join(lines) + "\n"


def run_source_health_check(analyzer: NewsAnalyzer) -> dict:
    service_dir = SERVICE_DIRS.get(analyzer.topic_key)
    if not service_dir or not service_dir.exists():
        raise RuntimeError(f"No crawler service configured for topic: {analyzer.topic_key}")

    helper = Path(__file__).resolve().parent / "source_health_check.py"
    if not helper.exists():
        raise RuntimeError(f"Health check helper not found: {helper}")

    logger.info("Checking crawler source health: %s", service_dir)
    completed = subprocess.run(
        [_service_python(service_dir), str(helper)],
        cwd=str(service_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=int(os.getenv("NEWS_HEALTH_TOTAL_TIMEOUT", "600")),
    )
    combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise RuntimeError(f"Health check failed with exit code {completed.returncode}:\n{combined_output}")

    payload = _extract_health_payload(combined_output)
    report_dir = Path(__file__).resolve().parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = report_dir / f"source_health_{analyzer.topic_key}_{stamp}.json"
    md_path = report_dir / f"source_health_{analyzer.topic_key}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_format_health_markdown(analyzer, payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["report_path"] = str(md_path)
    return payload


def analyze_latest():
    args = parse_args()
    analyzer = NewsAnalyzer(topic=args.topic)

    if args.health_check:
        payload = run_source_health_check(analyzer)
        summary = payload.get("summary", {})
        print("\n" + "=" * 60)
        print(f"Source health check complete for {analyzer.topic_label}.")
        print(f"Report: {payload.get('report_path', '')}")
        print(f"JSON:   {payload.get('json_path', '')}")
        print(
            "Summary: "
            f"ok={summary.get('ok', 0)}, "
            f"recovered={summary.get('recovered', 0) + summary.get('recovered_warn', 0)}, "
            f"warn={summary.get('warn', 0)}, "
            f"error={summary.get('error', 0)}"
        )
        print("=" * 60)
        return

    if args.refresh:
        json_path = refresh_topic_data(analyzer)
    elif args.data:
        json_path = args.data
    else:
        json_files = sorted(analyzer.data_dir.glob("news_*.json"))
        if not json_files:
            logger.error("No news JSON files found in %s", analyzer.data_dir)
            sys.exit(1)
        json_path = str(json_files[-1])

    logger.info("Topic: %s (%s)", analyzer.topic_key, analyzer.topic_label)
    logger.info("Analyzing: %s", json_path)
    logger.info("Report date: %s", args.date or "today")
    results = analyzer.analyze_json_file(json_path, date=args.date)

    if results.get("report"):
        print("\n" + "=" * 60)
        print(f"Analysis complete for {analyzer.topic_label}.")
        print(f"Report: {results.get('report_path', '')}")
        print(f"Brief:  {results.get('brief_path', '')}")
        print("=" * 60)
        print(results["report"][:500])


if __name__ == "__main__":
    analyze_latest()
