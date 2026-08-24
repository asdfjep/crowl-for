"""
HS News Service - 后台管理应用 (FastAPI + Jinja2)
对应 news_aggregator 后台管理功能：
- 订阅源管理 (增删改查 + 手动触发爬取)
- 分类管理 (关键词配置)
- 系统设置
- 文章浏览
- 爬取日志
"""
import os
import time
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .models import init_db, seed_default_categories, seed_default_sources, seed_default_config
from .database import SourceManager, CategoryManager, ArticleManager, CrawlLogManager, ConfigManager
from .scheduler import Scheduler

# ========== 路径设置 ==========
ADMIN_DIR = Path(__file__).parent.parent / "admin"
TEMPLATES_DIR = ADMIN_DIR / "templates"
STATIC_DIR = ADMIN_DIR / "static"
DB_PATH = Path(__file__).parent.parent / "data" / "hs_news.db"

DB_PATH.parent.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ========== 数据库初始化 ==========
engine, Session = init_db(str(DB_PATH))

def get_session():
    return Session()

# 种子数据
with get_session() as session:
    seed_default_categories(session)
    seed_default_sources(session)
    seed_default_config(session)

# ========== FastAPI 应用 ==========
app = FastAPI(title="HS News Admin", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key="hs-news-admin-secret-2026")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 添加自定义过滤器
templates.env.filters['datetime'] = lambda x: x.strftime('%Y-%m-%d %H:%M') if x else 'N/A'
templates.env.filters['json_parse'] = lambda x: json.loads(x) if x else {}

# 注入 Flask 风格的 get_flashed_messages 供模板使用
templates.env.globals['get_flashed_messages'] = lambda with_categories=False: []

# 调度器实例（延迟初始化）
scheduler_instance: Optional[Scheduler] = None


def set_scheduler(scheduler: Scheduler):
    """设置调度器实例供管理后台调用"""
    global scheduler_instance
    scheduler_instance = scheduler


# ========== 模板渲染辅助 ==========
def _get_stats(session):
    """获取统计信息"""
    return {
        'total_articles': ArticleManager.count(session),
        'total_sources': session.query(type(SourceManager.get_all(session).__class__.__bases__[0]())).count() if False else len(SourceManager.get_all(session)),
        'active_sources': len(SourceManager.get_active(session)),
        'total_categories': len(CategoryManager.get_all(session)),
        'total_logs': session.query(type(CrawlLogManager.get_recent(session).__class__.__bases__[0]())).count() if False else len(CrawlLogManager.get_recent(session, limit=99999)),
    }


def _read_config(session, key, default):
    return ConfigManager.get(session, key, default)


# ========== 前端路由 ==========
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session = get_session()
    try:
        articles = ArticleManager.get_all(session, limit=50)
        categories = CategoryManager.get_all(session)
        stats = {
            'total_articles': ArticleManager.count(session),
            'total_sources': len(SourceManager.get_all(session)),
            'active_sources': len(SourceManager.get_active(session)),
        }
        return templates.TemplateResponse("index.html", {
            "request": request,
            "articles": articles,
            "categories": categories,
            "stats": stats,
        })
    finally:
        session.close()


@app.get("/category/{category_name}", response_class=HTMLResponse)
async def category_page(request: Request, category_name: str):
    session = get_session()
    try:
        articles = ArticleManager.get_by_category(session, category_name, limit=100)
        return templates.TemplateResponse("category.html", {
            "request": request,
            "articles": articles,
            "category_name": category_name,
        })
    finally:
        session.close()


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    session = get_session()
    try:
        article = ArticleManager.get_by_id(session, article_id)
        if not article:
            raise HTTPException(status_code=404, detail="文章不存在")
        return templates.TemplateResponse("article.html", {
            "request": request,
            "article": article,
        })
    finally:
        session.close()


# ========== 后台管理路由 ==========

# Dashboard
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    session = get_session()
    try:
        sources = SourceManager.get_all(session)
        logs = CrawlLogManager.get_recent(session, limit=20)
        cat_counts = ArticleManager.count_by_category(session)
        categories = CategoryManager.get_all(session)

        # 按来源统计
        source_stats = []
        for src in sources:
            source_stats.append({
                'id': src.id,
                'name': src.name,
                'is_active': src.is_active,
                'last_status': src.last_crawl_status,
                'article_count_last': src.article_count_last,
                'total_articles': src.total_articles,
                'last_crawl_time': src.last_crawl_time,
                'error_message': src.error_message,
            })

        return templates.TemplateResponse("admin/dashboard.html", {
            "request": request,
            "sources": source_stats,
            "logs": logs,
            "categories": categories,
            "cat_counts": cat_counts,
            "stats": {
                'total_articles': ArticleManager.count(session),
                'total_sources': len(sources),
                'active_sources': len(SourceManager.get_active(session)),
                'total_categories': len(categories),
            },
        })
    finally:
        session.close()


# ----- 订阅源管理 -----
@app.get("/admin/sources", response_class=HTMLResponse)
async def admin_sources(request: Request):
    session = get_session()
    try:
        sources = SourceManager.get_all(session)
        return templates.TemplateResponse("admin/sources.html", {
            "request": request,
            "sources": sources,
        })
    finally:
        session.close()


@app.get("/admin/sources/add", response_class=HTMLResponse)
async def admin_source_add_form(request: Request):
    session = get_session()
    try:
        categories = CategoryManager.get_all(session)
        return templates.TemplateResponse("admin/source_form.html", {
            "request": request,
            "source": None,
            "categories": categories,
            "action": "add",
        })
    finally:
        session.close()


@app.post("/admin/sources/add")
async def admin_source_add(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    category: str = Form('general'),
    crawler_type: str = Form('async'),
    crawler_module: str = Form(''),
    crawl_interval: int = Form(1800),
    timeout: int = Form(45),
):
    session = get_session()
    try:
        if not name or not url:
            return RedirectResponse(url="/admin/sources/add?error=请填写完整信息", status_code=303)
        SourceManager.add(session, name=name, url=url, category=category,
                          crawler_type=crawler_type, crawler_module=crawler_module,
                          crawl_interval=crawl_interval, timeout=timeout)
        return RedirectResponse(url="/admin/sources?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/sources/edit/{source_id}", response_class=HTMLResponse)
async def admin_source_edit_form(request: Request, source_id: int):
    session = get_session()
    try:
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            raise HTTPException(status_code=404)
        categories = CategoryManager.get_all(session)
        return templates.TemplateResponse("admin/source_form.html", {
            "request": request,
            "source": source,
            "categories": categories,
            "action": "edit",
        })
    finally:
        session.close()


@app.post("/admin/sources/edit/{source_id}")
async def admin_source_edit(
    request: Request, source_id: int,
    name: str = Form(...),
    url: str = Form(...),
    category: str = Form('general'),
    crawler_type: str = Form('async'),
    crawler_module: str = Form(''),
    crawl_interval: int = Form(1800),
    timeout: int = Form(45),
    is_active: Optional[str] = Form(None),
):
    session = get_session()
    try:
        SourceManager.update(session, source_id, name=name, url=url, category=category,
                             crawler_type=crawler_type, crawler_module=crawler_module,
                             crawl_interval=crawl_interval, timeout=timeout,
                             is_active=(is_active == 'on'))
        return RedirectResponse(url="/admin/sources?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/sources/toggle/{source_id}")
async def admin_source_toggle(request: Request, source_id: int):
    """切换数据源启用/禁用状态"""
    session = get_session()
    try:
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            raise HTTPException(status_code=404)
        SourceManager.update(session, source_id, is_active=not source.is_active)
        return RedirectResponse(url="/admin/sources?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/sources/delete/{source_id}")
async def admin_source_delete(request: Request, source_id: int):
    session = get_session()
    try:
        SourceManager.delete(session, source_id)
        return RedirectResponse(url="/admin/sources?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/sources/crawl/{source_id}")
async def admin_source_crawl(request: Request, source_id: int):
    """手动触发单个源爬取"""
    session = get_session()
    try:
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            raise HTTPException(status_code=404)

        start_time = time.time()
        try:
            # 动态导入爬虫模块
            import importlib
            module = importlib.import_module(f"sources.{source.crawler_module}")
            
            # 查找爬虫类
            crawler_cls = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr_name.endswith('Crawler'):
                    crawler_cls = attr
                    break
            
            if not crawler_cls:
                raise ValueError(f"No crawler class found in sources.{source.crawler_module}")

            async def do_crawl():
                async with crawler_cls() as crawler:
                    return await asyncio.wait_for(crawler.fetch_news(), timeout=source.timeout)

            news_items = await do_crawl()

            # 保存文章
            new_count = 0
            for item in news_items:
                cat_name = CategoryManager.match(session, item.title, item.summary or '')
                ArticleManager.add(
                    session,
                    title=item.title, url=item.url,
                    source_id=source.id, source_name=source.name,
                    summary=item.summary, category=cat_name,
                    severity=item.severity, location=item.location,
                    latitude=item.latitude, longitude=item.longitude,
                    publish_time=item.publish_time,
                )
                new_count += 1

            SourceManager.update_crawl_status(
                session, source.id, 'success',
                articles_found=len(news_items), articles_new=new_count
            )
            CrawlLogManager.add(
                session, source.id, source.name, 'success',
                articles_found=len(news_items), articles_new=new_count,
                duration_seconds=time.time() - start_time
            )
        except Exception as e:
            SourceManager.update_crawl_status(session, source.id, 'failed', error_message=str(e))
            CrawlLogManager.add(
                session, source.id, source.name, 'failed',
                error_message=str(e), duration_seconds=time.time() - start_time
            )

        return RedirectResponse(url="/admin/sources?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/sources/crawl_all")
async def admin_crawl_all(request: Request):
    """触发所有源爬取"""
    session = get_session()
    try:
        if scheduler_instance:
            # 使用调度器执行单次爬取
            asyncio.create_task(scheduler_instance.run())
            return RedirectResponse(url="/admin?success=1", status_code=303)
        return RedirectResponse(url="/admin?error=调度器未初始化", status_code=303)
    finally:
        session.close()


# ----- 分类管理 -----
@app.get("/admin/categories", response_class=HTMLResponse)
async def admin_categories(request: Request):
    session = get_session()
    try:
        categories = CategoryManager.get_all(session)
        cat_counts = ArticleManager.count_by_category(session)
        return templates.TemplateResponse("admin/categories.html", {
            "request": request,
            "categories": categories,
            "cat_counts": cat_counts,
        })
    finally:
        session.close()


@app.post("/admin/categories/add")
async def admin_category_add(
    request: Request,
    name: str = Form(...),
    keywords: str = Form(''),
    description: str = Form(''),
    priority: int = Form(10),
    color: str = Form('#6366f1'),
):
    session = get_session()
    try:
        CategoryManager.add(session, name=name, keywords=keywords,
                            description=description, priority=priority, color=color)
        return RedirectResponse(url="/admin/categories?success=1", status_code=303)
    finally:
        session.close()


@app.post("/admin/categories/edit/{cat_id}")
async def admin_category_edit(
    request: Request, cat_id: int,
    name: str = Form(...),
    keywords: str = Form(''),
    description: str = Form(''),
    priority: int = Form(10),
    color: str = Form('#6366f1'),
    is_active: Optional[str] = Form(None),
):
    session = get_session()
    try:
        CategoryManager.update(session, cat_id, name=name, keywords=keywords,
                               description=description, priority=priority, color=color,
                               is_active=(is_active == 'on'))
        return RedirectResponse(url="/admin/categories?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/categories/delete/{cat_id}")
async def admin_category_delete(request: Request, cat_id: int):
    session = get_session()
    try:
        CategoryManager.delete(session, cat_id)
        return RedirectResponse(url="/admin/categories?success=1", status_code=303)
    finally:
        session.close()


# ----- 文章管理 -----
@app.get("/admin/articles", response_class=HTMLResponse)
async def admin_articles(request: Request, category: str = 'all'):
    session = get_session()
    try:
        if category == 'all':
            articles = ArticleManager.get_all(session, limit=200)
        else:
            articles = ArticleManager.get_by_category(session, category, limit=200)
        categories = CategoryManager.get_all(session)
        return templates.TemplateResponse("admin/articles.html", {
            "request": request,
            "articles": articles,
            "categories": categories,
            "current_category": category,
        })
    finally:
        session.close()


@app.get("/admin/articles/delete/{article_id}")
async def admin_article_delete(request: Request, article_id: int):
    session = get_session()
    try:
        ArticleManager.delete(session, article_id)
        return RedirectResponse(url="/admin/articles?success=1", status_code=303)
    finally:
        session.close()


@app.get("/admin/articles/clear_old")
async def admin_articles_clear_old(request: Request, days: int = 30):
    session = get_session()
    try:
        count = ArticleManager.clear_old(session, days=days)
        return RedirectResponse(url=f"/admin/articles?success=1&cleared={count}", status_code=303)
    finally:
        session.close()


# ----- 爬取日志 -----
@app.get("/admin/logs", response_class=HTMLResponse)
async def admin_logs(request: Request):
    session = get_session()
    try:
        logs = CrawlLogManager.get_recent(session, limit=100)
        return templates.TemplateResponse("admin/logs.html", {
            "request": request,
            "logs": logs,
        })
    finally:
        session.close()


@app.get("/admin/logs/clear_old")
async def admin_logs_clear_old(request: Request, days: int = 7):
    session = get_session()
    try:
        count = CrawlLogManager.clear_old(session, days=days)
        return RedirectResponse(url=f"/admin/logs?success=1&cleared={count}", status_code=303)
    finally:
        session.close()


# ----- 系统设置 -----
@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    session = get_session()
    try:
        configs = ConfigManager.get_all(session)
        return templates.TemplateResponse("admin/settings.html", {
            "request": request,
            "configs": {c.key: c for c in configs},
        })
    finally:
        session.close()


@app.post("/admin/settings")
async def admin_settings_save(request: Request):
    session = get_session()
    try:
        form = await request.form()
        for key, value in form.items():
            if key.startswith('cfg_'):
                cfg_key = key[4:]
                ConfigManager.set(session, cfg_key, value)
        return RedirectResponse(url="/admin/settings?success=1", status_code=303)
    finally:
        session.close()


# ----- API 接口 -----
@app.get("/api/stats")
async def api_stats():
    session = get_session()
    try:
        return {
            'total_articles': ArticleManager.count(session),
            'total_sources': len(SourceManager.get_all(session)),
            'active_sources': len(SourceManager.get_active(session)),
            'categories': len(CategoryManager.get_all(session)),
        }
    finally:
        session.close()


@app.get("/api/sources")
async def api_sources():
    session = get_session()
    try:
        sources = SourceManager.get_all(session)
        return [s.to_dict() for s in sources]
    finally:
        session.close()


@app.get("/api/categories")
async def api_categories():
    session = get_session()
    try:
        categories = CategoryManager.get_all(session)
        return [c.to_dict() for c in categories]
    finally:
        session.close()


@app.get("/api/articles/recent")
async def api_articles_recent(limit: int = 50):
    session = get_session()
    try:
        articles = ArticleManager.get_all(session, limit=limit)
        return [a.to_dict() for a in articles]
    finally:
        session.close()


@app.get("/api/logs/recent")
async def api_logs_recent(limit: int = 50):
    session = get_session()
    try:
        logs = CrawlLogManager.get_recent(session, limit=limit)
        return [l.to_dict() for l in logs]
    finally:
        session.close()
