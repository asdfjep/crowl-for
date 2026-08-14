"""
AI News Analyzer - FastAPI Server
接收抓取模块推送的JSON数据，返回分析报告
"""
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI News Analyzer", version="1.0.0")

from services.analyzer import NewsAnalyzer

analyzer = NewsAnalyzer()


def _resolve_data_dir() -> Path:
    override = os.getenv("NEWS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "data"


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


@app.get("/api/reports")
async def list_reports():
    """列出已有报告"""
    report_dir = Path(analyzer.reporter.report_dir)
    if not report_dir.exists():
        return {"reports": []}
    
    reports = sorted(
        list(report_dir.glob("daily_report_*.md"))
        + list(report_dir.glob("*_weekly_report_*.md"))
        + list(report_dir.glob("daily_brief_*.html"))
        + list(report_dir.glob("*_weekly_brief_*.html")),
        key=lambda r: r.stat().st_mtime,
        reverse=True,
    )
    return {
        "reports": [
            {
                "name": r.name,
                "size": r.stat().st_size,
                "modified": datetime.fromtimestamp(r.stat().st_mtime).isoformat(),
            }
            for r in reports[:50]
        ]
    }


@app.get("/api/reports/{report_name}")
async def get_report(report_name: str):
    """获取指定报告内容"""
    report_dir = Path(analyzer.reporter.report_dir)
    report_file = report_dir / report_name
    
    # 安全校验：防止路径穿越
    if not report_file.exists() or not report_file.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    
    if not report_file.resolve().is_relative_to(report_dir.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {"name": report_name, "content": content}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
