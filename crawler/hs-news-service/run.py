#!/usr/bin/env python3
"""
HS News Crawler Service - 主入口
支持两种模式：
1. 仅爬虫：python run.py
2. 爬虫 + 管理后台：python run.py --admin [--port 8000]
"""
import asyncio
import sys
import os
import argparse
from typing import Optional

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.scheduler import Scheduler
from app.admin_app import app as admin_app, set_scheduler


def main():
    parser = argparse.ArgumentParser(description="HS News Crawler Service")
    parser.add_argument("--admin", action="store_true", help="启动 Web 管理后台")
    parser.add_argument("--port", type=int, default=8000, help="管理后台端口 (默认 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="管理后台绑定地址")
    parser.add_argument("--interval", type=int, default=60, help="爬取间隔（分钟）")
    parser.add_argument("--once", action="store_true", help="仅执行一次爬取后退出")
    parser.add_argument("--push-url", type=str, default=None, help="分析服务推送地址 (覆盖环境变量和DB配置)")
    args = parser.parse_args()

    if args.admin:
        # 模式 1: 爬虫 + 管理后台 (uvicorn)
        run_with_admin(args)
    elif args.once:
        # 模式 2: 仅执行一次爬取
        run_once(push_url=args.push_url)
    else:
        # 模式 3: 仅爬虫循环运行
        run_crawler_only(args.interval, push_url=args.push_url)


def run_once(push_url: Optional[str] = None):
    """执行一次爬取后退出"""
    async def _run():
        scheduler = Scheduler(push_url=push_url)
        await scheduler.load_sources()
        await scheduler.run()

    asyncio.run(_run())


def run_crawler_only(interval_minutes: int, push_url: Optional[str] = None):
    """仅运行爬虫循环"""
    async def _run():
        scheduler = Scheduler(push_url=push_url)
        await scheduler.load_sources()
        await scheduler.run_forever(interval_minutes)

    asyncio.run(_run())


def run_with_admin(args):
    """运行爬虫 + 管理后台"""
    import uvicorn

    # 创建调度器实例
    scheduler = Scheduler(push_url=args.push_url)

    # 同步加载数据源（用于 admin_app 中的手动爬取）
    async def _load():
        await scheduler.load_sources()

    asyncio.get_event_loop().run_until_complete(_load())

    # 设置调度器到管理后台
    set_scheduler(scheduler)

    # 启动 uvicorn
    print(f"Starting HS News Admin on http://{args.host}:{args.port}")
    print("=" * 50)
    uvicorn.run("app.admin_app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
