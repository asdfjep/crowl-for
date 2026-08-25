"""
AI News Analyzer - FastAPI Server
接收抓取模块推送的JSON数据，返回分析报告；并为 Web 管理前端提供 API。
"""
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_local_llm_config() -> None:
    """Load machine-local LLM defaults so LLM polish (weekly-report Chinese
    translation) works through the web API, mirroring run_llm.py."""
    config_path = Path(__file__).with_name("llm_config.local.json")
    if not config_path.exists():
        return
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load %s: %s", config_path, exc)
        return
    env_map = {
        "api_key": "NEWS_LLM_API_KEY",
        "base_url": "NEWS_LLM_BASE_URL",
        "model": "NEWS_LLM_MODEL",
        "timeout": "NEWS_LLM_TIMEOUT",
    }
    for key, env_name in env_map.items():
        value = str(config.get(key, "")).strip()
        if value:
            os.environ.setdefault(env_name, value)


_load_local_llm_config()

app = FastAPI(title="AI News Analyzer", version="1.0.0")

from services.analyzer import NewsAnalyzer

analyzer = NewsAnalyzer()

from server_jobs import JobManager, list_topics_config, resolve_topic_data_dir

job_manager = JobManager(max_workers=1)
job_manager.start()


def _resolve_data_dir() -> Path:
    override = os.getenv("NEWS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "data"


def _resolve_report_dir() -> Path:
    override = os.getenv("NEWS_REPORT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "reports"


def _write_json_artifact(payload: dict, filename: str) -> Path:
    data_dir = _resolve_data_dir()
    output_file = data_dir / filename
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        return output_file
    except OSError as exc:
        fallback_dir = Path(tempfile.gettempdir()) / "unified-news-analyzer" / "data"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_file = fallback_dir / filename
        with open(fallback_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        logger.warning(
            "Failed to save raw data to %s, fell back to %s: %s",
            output_file,
            fallback_file,
            exc,
        )
        return fallback_file


class AnalyzeRequest(BaseModel):
    """分析请求"""
    news: list  # 新闻列表
    sources: Optional[list] = None  # 数据源名称列表
    date: Optional[str] = None  # 日期 YYYY-MM-DD
    save_json: Optional[bool] = True  # 是否保存原始数据


class AnalyzeResponse(BaseModel):
    """分析响应"""
    success: bool
    summary: dict
    report_path: Optional[str] = None
    brief_path: Optional[str] = None
    top_events: list


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_news(req: AnalyzeRequest):
    """接收抓取数据，返回分析结果"""
    try:
        logger.info(f"Received {len(req.news)} news items from {len(req.sources or [])} sources")

        results = analyzer.analyze(
            news_list=req.news,
            sources=req.sources or [],
            date=req.date or datetime.now().strftime('%Y-%m-%d'),
        )

        # 如果需要，保存原始JSON
        if req.save_json and req.sources:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = _write_json_artifact({
                'crawlTime': datetime.now().isoformat(),
                'sources': req.sources,
                'news': req.news,
            }, f"news_{timestamp}.json")
            logger.info(f"Saved raw data to {output_file}")

        # 构造返回摘要
        all_clusters = results.get('ranked_clusters', [])
        top_clusters = all_clusters[:10]
        board_summary = results.get('board_summary', {})

        summary = {
            'input_count': results.get('dedup', {}).get('input_count', 0),
            'unique_count': results.get('dedup', {}).get('unique_count', 0),
            'duplicate_count': results.get('dedup', {}).get('duplicate_count', 0),
            'cluster_count': len(all_clusters),
            'board_count': len(board_summary),
        }

        top_events = [
            {
                'title': c.get('representative_title', ''),
                'score': c.get('importance_score', 0),
                'sources': c.get('sources', []),
                'count': c.get('item_count', 0),
            }
            for c in top_clusters
        ]

        return AnalyzeResponse(
            success=True,
            summary=summary,
            top_events=top_events,
            report_path=results.get('report_path', ''),
            brief_path=results.get('brief_path', ''),
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "ai-news-analyzer"}


# ============ Web 管理前端 API ============

REPORT_GLOBS = [
    ("weekly_md", "*_weekly_report_*.md"),
    ("weekly_pdf", "*_weekly_report_*.pdf"),
    ("daily_md", "daily_report_*.md"),
    ("daily_pdf", "daily_report_*.pdf"),
    ("brief_html", ["*_weekly_brief_*.html", "daily_brief_*.html"]),
    ("health_md", "source_health_*.md"),
    ("health_json", "source_health_*.json"),
]


def _topic_from_report_name(name: str) -> str:
    for key in ("commercial_space", "display_polarizer", "ai"):
        if name.startswith(f"{key}_"):
            return key
    return ""


def _scan_reports(limit: int = 200):
    report_dir = _resolve_report_dir()
    entries = []
    if report_dir.exists():
        for category, patterns in REPORT_GLOBS:
            if isinstance(patterns, str):
                patterns = [patterns]
            for pattern in patterns:
                for path in report_dir.glob(pattern):
                    entries.append({
                        "name": path.name,
                        "category": category,
                        "topic": _topic_from_report_name(path.name),
                        "size": path.stat().st_size,
                        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    })
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries[:limit]


def _safe_report_path(name: str) -> Optional[Path]:
    report_dir = _resolve_report_dir()
    if not report_dir.exists():
        return None
    candidate = (report_dir / name).resolve()
    if not candidate.is_relative_to(report_dir.resolve()):
        return None
    if not candidate.is_file():
        return None
    return candidate


@app.get("/api/meta")
async def meta():
    from services.llm_config import load_config

    topics = list_topics_config()
    llm_cfg = load_config()
    llm_ready = bool(
        llm_cfg.get("base_url")
        and (llm_cfg.get("api_key") or os.getenv("NEWS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
    )
    reports = _scan_reports(limit=10000)
    counts = {}
    for entry in reports:
        if entry["category"] in ("weekly_md", "daily_md"):
            counts["report_md"] = counts.get("report_md", 0) + 1
        elif entry["category"] in ("weekly_pdf", "daily_pdf"):
            counts["report_pdf"] = counts.get("report_pdf", 0) + 1
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1

    return {
        "service": "ai-news-analyzer",
        "version": app.version,
        "status": "ok",
        "topics": topics,
        "report_dir": str(_resolve_report_dir()),
        "data_dir": str(_resolve_data_dir()),
        "llm_ready": llm_ready,
        "report_stats": counts,
        "python": sys.version.split()[0],
    }


class LlmConfigRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = None


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "…" + key[-4:]


@app.get("/api/llm-config")
async def get_llm_config():
    """返回当前 LLM 配置（api_key 脱敏）。"""
    from services.llm_config import apply_llm_env, load_config

    apply_llm_env()
    cfg = load_config()
    key = cfg.get("api_key") or os.getenv("NEWS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    return {
        "configured": bool(cfg.get("base_url") and key),
        "base_url": cfg.get("base_url") or os.getenv("NEWS_LLM_BASE_URL") or "https://api.openai.com/v1",
        "model": cfg.get("model") or os.getenv("NEWS_LLM_MODEL") or "gpt-4o-mini",
        "timeout": cfg.get("timeout") or 60,
        "api_key_set": bool(key),
        "api_key_masked": _mask_key(key),
    }


@app.put("/api/llm-config")
async def update_llm_config(req: LlmConfigRequest):
    """保存 LLM 配置到数据目录并生效（api_key 留空表示沿用已有的）。"""
    from services.llm_config import apply_llm_env, load_config, save_config

    existing = load_config()
    api_key = str(req.api_key).strip() if req.api_key else existing.get("api_key") or ""
    cfg = {
        "api_key": api_key,
        "base_url": (req.base_url or existing.get("base_url") or "").strip(),
        "model": (req.model or existing.get("model") or "").strip(),
        "timeout": int(req.timeout or existing.get("timeout") or 60),
    }
    if not cfg["base_url"] or not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="base_url 和 api_key 不能同时为空")
    path = save_config(cfg)
    apply_llm_env()
    return {
        "ok": True,
        "path": str(path),
        "configured": True,
        "api_key_masked": _mask_key(cfg["api_key"]),
    }


@app.post("/api/llm-config/test")
async def test_llm_config(req: Optional[LlmConfigRequest] = None):
    """用请求中的候选配置（可先测再保存）或当前配置做一次连通性测试。"""
    from services.llm_config import apply_llm_env, chat_completion
    from services.llm_config import _ENV_MAP  # noqa

    saved = None
    if req is not None:
        from services.llm_config import load_config

        existing = load_config()
        saved = {
            "base_url": os.getenv("NEWS_LLM_BASE_URL"),
            "api_key": os.getenv("NEWS_LLM_API_KEY"),
            "model": os.getenv("NEWS_LLM_MODEL"),
        }
        api_key = str(req.api_key).strip() if req.api_key else existing.get("api_key") or ""
        base_url = (req.base_url or existing.get("base_url") or "").strip()
        model = (req.model or existing.get("model") or "").strip()
        os.environ["NEWS_LLM_API_KEY"] = api_key
        os.environ["NEWS_LLM_BASE_URL"] = base_url or "https://api.openai.com/v1"
        os.environ["NEWS_LLM_MODEL"] = model or "gpt-4o-mini"
    else:
        apply_llm_env()

    try:
        reply = chat_completion("请仅回复两个字：成功", system=None, max_tokens=8)
        return {"ok": True, "reply": reply}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        if saved is not None:
            os.environ["NEWS_LLM_API_KEY"] = saved["api_key"] or ""
            os.environ["NEWS_LLM_BASE_URL"] = saved["base_url"] or ""
            os.environ["NEWS_LLM_MODEL"] = saved["model"] or ""


@app.get("/api/reports")
async def list_reports():
    """列出已有报告"""
    return {"reports": _scan_reports()}


@app.get("/api/reports/{report_name}")
async def get_report(report_name: str):
    """获取指定报告内容；.md/.json 返回文本，.html/.pdf 流式返回"""
    sub = _safe_report_path(report_name)
    if sub is None:
        raise HTTPException(status_code=404, detail="Report not found")

    suffix = Path(report_name).suffix.lower()
    if suffix in {".pdf"}:
        return FileResponse(
            sub,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{sub.name}"'},
        )
    if suffix in {".html", ".htm"}:
        return FileResponse(sub, media_type="text/html; charset=utf-8")
    with open(sub, 'r', encoding='utf-8') as f:
        content = f.read()
    return {"name": report_name, "content": content}


@app.get("/api/data-files")
async def list_data_files():
    """列出各主题数据目录下的 news_*.json"""
    files = []
    seen = set()
    for topic in list_topics_config():
        from services.topic_config import load_topic_config

        try:
            config = load_topic_config(topic["key"])
        except Exception as exc:
            logger.warning("Skip topic data listing %s: %s", topic["key"], exc)
            continue
        data_dir = resolve_topic_data_dir(topic["key"], config)
        if not data_dir.exists():
            continue
        for path in sorted(data_dir.glob("news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.name in seen:
                continue
            seen.add(path.name)
            files.append({
                "topic": topic["key"],
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "item_count": _count_news_items(path),
            })
    return {"files": files}


def _count_news_items(path: Path) -> int:
    try:
        if path.stat().st_size > 50 * 1024 * 1024:
            return -1
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        news = data.get("news", []) if isinstance(data, dict) else []
        return len(news) if isinstance(news, list) else -1
    except Exception:
        return -1


def _find_data_file(name: str) -> Optional[Path]:
    if Path(name).name != name or name.startswith((".", "_")):
        return None
    dirs = [_resolve_data_dir()]
    for topic in list_topics_config():
        from services.topic_config import load_topic_config

        try:
            config = load_topic_config(topic["key"])
        except Exception:
            continue
        dirs.append(resolve_topic_data_dir(topic["key"], config))
    for data_dir in dict.fromkeys(dirs):
        if not data_dir.exists():
            continue
        candidate = (data_dir / name).resolve()
        if candidate.is_file() and candidate.is_relative_to(data_dir.resolve()):
            return candidate
    return None


@app.get("/api/data-files/{file_name}")
async def get_data_file(file_name: str):
    """查看某个数据文件的元信息与前 20 条预览"""
    path = _find_data_file(file_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Data file not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"数据文件读取失败: {exc}")
    news = data.get("news", []) if isinstance(data, dict) else []
    items = news[:20] if isinstance(news, list) else []
    preview = [
        {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "publishTime": item.get("publishTime", ""),
            "url": item.get("url", ""),
        }
        for item in items
    ]
    return {
        "name": file_name,
        "crawlTime": data.get("crawlTime", "") if isinstance(data, dict) else "",
        "sources": data.get("sources", []) if isinstance(data, dict) else [],
        "item_count": len(news) if isinstance(news, list) else -1,
        "preview": preview,
    }


class UploadDataRequest(BaseModel):
    topic: Optional[str] = "ai"
    payload: dict


@app.post("/api/data-files")
async def create_data_file(req: UploadDataRequest):
    """保存一份新闻数据 JSON 到主题数据目录"""
    topic = (req.topic or "ai").strip()
    from services.topic_config import load_topic_config

    try:
        config = load_topic_config(topic)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    news = req.payload.get("news", [])
    if not isinstance(news, list):
        raise HTTPException(status_code=400, detail="payload.news 必须是数组")
    data_dir = resolve_topic_data_dir(topic, config)
    data_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"news_{timestamp}.json"
    (data_dir / filename).write_text(
        json.dumps(req.payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "topic": topic,
        "name": filename,
        "path": str(data_dir / filename),
        "item_count": len(news),
    }


class CreateJobRequest(BaseModel):
    kind: str
    payload: Optional[dict] = None


@app.post("/api/jobs")
async def create_job(req: CreateJobRequest):
    """提交后台任务：kind=analyze（分析）/ health（源巡检）"""
    if req.kind not in {"analyze", "health"}:
        raise HTTPException(status_code=400, detail=f"Unsupported job kind: {req.kind}")
    if req.kind == "analyze":
        data = (req.payload or {}).get("data")
        if data is not None and not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="payload.data 必须是 {news, sources, ...} 对象")
    job = job_manager.submit(req.kind, req.payload or {})
    return {"job": job_manager.get(job["id"])}


@app.get("/api/jobs")
async def list_jobs(limit: int = 50):
    return {"jobs": job_manager.list(limit)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)