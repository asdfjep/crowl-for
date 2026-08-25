"""
Background job manager for the AI News Analyzer web API.

Runs analysis / health-check tasks in a small serialized worker pool so the
FastAPI process never blocks on long-running report generation.
"""
import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

# Mirror run_llm.py defaults so an "LLM polish" run reproduces CLI behavior.
LLM_ENV_DEFAULTS = {
    "NEWS_SUMMARY_MODE": "local",
    "NEWS_SUMMARY_USE_AI": "0",
    "NEWS_LLM_POLISH": "1",
    "NEWS_LLM_BROAD_RECALL": "1",
    "NEWS_LLM_BOARD_MIN_ITEMS": "2",
    "NEWS_LLM_BOARD_MAX_ITEMS": "5",
    "NEWS_LLM_BOARD_CANDIDATE_ITEMS": "24",
    "NEWS_REPORT_VARIANT": "llm",
}


def resolve_topic_data_dir(topic_key: str, config: Dict[str, Any]) -> Path:
    """Data dir for a topic, falling back to NEWS_DATA_DIR / project data dir.

    Topic configs may point at crawler-adjacent directories (../../.tmp_...)
    that only exist on the original Windows machine; on a deployed server we
    fall back to the env override or the shared data/ directory.
    """
    configured = config.get("_data_dir")
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            return candidate
    override = os.getenv("NEWS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    # Configured dir absent (e.g. fresh server without crawler services):
    # fall back to the project's shared data directory.
    return PROJECT_ROOT / "data"


def list_topics_config() -> List[Dict[str, Any]]:
    from services.topic_config import TOPIC_CONFIG_DIR, load_topic_config

    topics = []
    for path in sorted(TOPIC_CONFIG_DIR.glob("*.json")):
        if path.name.startswith("."):
            continue
        key = path.stem
        try:
            config = load_topic_config(key)
        except Exception as exc:
            logger.warning("Skip topic config %s: %s", key, exc)
            continue
        boards = config.get("boards", {}) or {}
        topics.append({
            "key": config["topic_key"],
            "label": config.get("label", key),
            "report_prefix": config.get("report_prefix", key),
            "board_order": boards.get("order", []),
            "source_count": len(config.get("sources", []) or []),
        })
    return topics


class JobManager:
    """In-memory serialized job queue."""

    def __init__(self, max_workers: int = 1):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._queue: List[str] = []
        self._cv = threading.Condition()
        self._stop = False
        self._threads: List[threading.Thread] = []
        self._max_workers = max_workers

    def start(self) -> None:
        for _ in range(self._max_workers):
            thread = threading.Thread(target=self._worker_loop, daemon=True, name="job-worker")
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def submit(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "kind": kind,
            "payload": payload,
            "status": "queued",
            "message": "排队中",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        with self._cv:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._queue.append(job_id)
            self._cv.notify()
        return job

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._cv:
            job = self._jobs.get(job_id)
            if not job:
                return None
            public = dict(job)
            public.pop("payload", None)
            return public

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._cv:
            ids = self._order[-limit:]
            out = []
            for job_id in ids:
                public = dict(self._jobs[job_id])
                public.pop("payload", None)
                out.append(public)
            return out

    def _worker_loop(self) -> None:
        while True:
            with self._cv:
                while not self._queue and not self._stop:
                    self._cv.wait()
                if self._stop and not self._queue:
                    return
                job_id = self._queue.pop(0)
                job = self._jobs[job_id]
                job["status"] = "running"
                job["started_at"] = datetime.now().isoformat(timespec="seconds")
                job["message"] = "运行中"

            try:
                result = run_job(job)
                with self._cv:
                    job["status"] = "success"
                    job["result"] = result
                    job["message"] = "完成"
            except Exception as exc:
                logger.exception("Job %s failed", job_id)
                with self._cv:
                    job["status"] = "error"
                    job["error"] = str(exc)
                    job["message"] = "失败"
            finally:
                with self._cv:
                    job["finished_at"] = datetime.now().isoformat(timespec="seconds")


def run_job(job: Dict[str, Any]):
    kind = job.get("kind")
    payload = job.get("payload") or {}
    if kind == "analyze":
        return run_analyze(payload)
    if kind == "health":
        return run_health_check(payload)
    raise ValueError(f"Unknown job kind: {kind!r}")


def run_analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = str(payload.get("topic") or os.getenv("NEWS_TOPIC") or "ai").strip()
    use_llm = bool(payload.get("use_llm"))
    date = payload.get("date") or None

    from services.topic_config import load_topic_config

    config = load_topic_config(topic)
    data_dir = resolve_topic_data_dir(topic, config)

    data = payload.get("data")
    data_file = payload.get("data_file")
    if data is None:
        if data_file:
            data_dir_resolved = data_dir.resolve()
            source = (data_dir_resolved / str(data_file)).resolve()
            if not source.is_relative_to(data_dir_resolved) or not source.is_file():
                raise ValueError(f"数据文件不可用: {data_file}")
            with open(source, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            files = sorted(data_dir.glob("news_*.json"), key=lambda p: p.stat().st_mtime)
            if not files:
                raise ValueError(f"主题 {topic} 数据目录中暂无 news_*.json 数据文件")
            with open(files[-1], encoding="utf-8") as fh:
                data = json.load(fh)

    news_list = data.get("news", []) if isinstance(data, dict) else data
    if not isinstance(news_list, list):
        raise ValueError("数据格式错误：news 字段必须是数组")
    sources = data.get("sources", []) if isinstance(data, dict) else []

    # Generate the human-readable HTML brief alongside the markdown report.
    os.environ["NEWS_GENERATE_HTML_BRIEF"] = "1"

    # Apply the LLM config saved in the web 「系统设置」 so every LLM need
    # (weekly-report polish, title translation) uses the same endpoint.
    from services.llm_config import apply_llm_env

    apply_llm_env()

    if use_llm:
        for key, value in LLM_ENV_DEFAULTS.items():
            os.environ.setdefault(key, value)
        from services.analyzer_llm import NewsAnalyzer
    else:
        from services.analyzer import NewsAnalyzer

    analyzer = NewsAnalyzer(topic=topic)
    results = analyzer.analyze(news_list, sources=sources, date=date)
    compact = _compact_analyze_result(results)
    report_path = compact.get("report_path") or ""
    brief_path = compact.get("brief_path") or ""
    if report_path:
        path = Path(report_path)
        if path.suffix.lower() == ".pdf":
            # report_path points at the PDF once it renders; the markdown twin
            # shares the same stem and is the human-readable primary.
            compact["report_name"] = path.with_suffix(".md").name
            compact["report_md_name"] = path.with_suffix(".md").name
            compact["report_pdf_name"] = path.name
        else:
            compact["report_name"] = path.name
            compact["report_md_name"] = path.name
            pdf = path.with_suffix(".pdf")
            if pdf.is_file():
                compact["report_pdf_name"] = pdf.name
    if brief_path:
        compact["brief_name"] = Path(brief_path).name
    return compact


def _compact_analyze_result(results: Dict[str, Any]) -> Dict[str, Any]:
    dedup = results.get("dedup", {}) or {}
    ranked = results.get("ranked_clusters", []) or []
    board_summary = results.get("board_summary", {}) or {}

    top_events = []
    for cluster in ranked[:10]:
        top_events.append({
            "title": cluster.get("representative_title", ""),
            "score": round(float(cluster.get("importance_score", 0) or 0), 1),
            "sources": (cluster.get("_all_sources") or cluster.get("sources") or [])[:10],
            "count": cluster.get("item_count", len(cluster.get("items", []) or [])),
            "board": _cluster_parent_board(cluster),
        })

    return {
        "period": results.get("period", {}),
        "summary": {
            "input_count": dedup.get("input_count", 0),
            "unique_count": dedup.get("unique_count", 0),
            "duplicate_count": dedup.get("duplicate_count", 0),
            "cluster_count": len(ranked),
            "board_count": len(board_summary),
        },
        "board_breakdown": _board_breakdown(board_summary),
        "top_events": top_events,
        "source_health": results.get("source_health", {}),
        "business_relevance": results.get("business_relevance", {}),
        "trends": results.get("trends", {}),
        "report_path": results.get("report_path", "") or "",
        "brief_path": results.get("brief_path", "") or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _cluster_parent_board(cluster: Dict[str, Any]) -> str:
    counts: "Counter[str]" = Counter()
    for item in cluster.get("items", []) or []:
        counts[item.get("parent_board", "A8 · 媒体评论")] += 1
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def _board_breakdown(board_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aggregate per parent board, ordered by item count desc."""
    groups: "Dict[str, Dict[str, int]]" = {}
    for data in board_summary.values():
        parent = data.get("parent_board", "其他")
        entry = groups.setdefault(parent, {"count": 0, "source_count": 0})
        entry["count"] += int(data.get("count", 0))
        entry["source_count"] += int(data.get("source_count", 0))
    rows = [{"parent_board": key, **value} for key, value in groups.items()]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows


def run_health_check(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = str(payload.get("topic") or "ai").strip()
    cmd = [sys.executable, "run.py", "--topic", topic, "--health-check"]
    timeout = int(os.getenv("NEWS_HEALTH_TOTAL_TIMEOUT", "600"))
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "topic": topic,
            "ok": False,
            "returncode": -1,
            "summary": f"巡检超时（>{timeout}s）",
            "report": "",
            "json": "",
            "output_tail": f"Health check exceeded {timeout}s timeout.",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)

    def extract(pattern: str) -> str:
        match = re.search(pattern, output, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    summary = extract(r"^Summary:\s*(.+)$")
    # A successful run always prints a "Summary: ..." line; treat runs that
    # only produced a traceback (e.g. missing crawler service) as failed.
    ok = completed.returncode == 0 and bool(summary)

    return {
        "topic": topic,
        "ok": ok,
        "returncode": completed.returncode,
        "summary": summary,
        "report": extract(r"^Report:\s*(.+)$"),
        "json": extract(r"^JSON:\s*(.+)$"),
        "output_tail": output[-4000:],
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }