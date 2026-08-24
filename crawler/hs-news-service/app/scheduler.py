"""
Scheduler Module - 增强版
支持从数据库读取配置、记录爬取日志、保存文章到数据库
"""
import asyncio
import os
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# 导入数据库模块
from app.models import init_db
from sources.base import NewsItem
from app.push import NewsPusher
from sources.base import NewsItem as BaseNewsItem
from app.database import SourceManager, CategoryManager, ArticleManager, CrawlLogManager, ConfigManager

# 数据库初始化
engine, Session = init_db(str(DATA_DIR / "hs_news.db"))


def get_db_session():
    """创建新的数据库会话"""
    return Session()

# 导入爬虫
from sources.base import NewsItem as BaseNewsItem
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

# Playwright crawlers
from sources.ofweek_pw import OFweekCrawler
from sources.kr36_pw import Kr36Crawler
from sources.boe_pw import BOECrawler
from sources.spacenews_pw import SpaceNewsCrawler

# HTML crawlers
from sources.aibusiness import AIBusinessCrawler
from sources.lgdisplay import LGDisplayCrawler

# 爬虫模块映射
CRAWLER_MAP = {
    "thsnews": ThsnewsCrawler,
    "aerospace": AerospaceCrawler,
    "ai_news": AINewsCrawler,
    "polarizer": PolarizerCrawler,
    "conflict_events": ConflictEventsCrawler,
    "financial_markets": FinancialMarketsCrawler,
    "cls": CLSCrawler,
    "displaydaily": DisplayDailyCrawler,
    "spacechina": SpaceChinaCrawler,
    "space_com": SpaceComCrawler,
    "nasa": NASACrawler,
    "the_decoder": TheDecoderCrawler,
    "synced": SyncedCrawler,
    "deepmind": DeepMindCrawler,
    "venturebeat": VentureBeatCrawler,
    "eu_ai": EUAICrawler,
    "leiphone": LeiphoneCrawler,
    "qbitai": QbitaiCrawler,
    "ofweek": OFweekCrawler,
    "36kr": Kr36Crawler,
    "boe": BOECrawler,
    "spacenews": SpaceNewsCrawler,
    "aibusiness": AIBusinessCrawler,
    "lgdisplay": LGDisplayCrawler,
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, use_db: bool = True, push_url: Optional[str] = None):
        self.sources = {}  # name -> crawler instance
        self.results = []
        self.is_running = False
        self.use_db = use_db
        self.push_url = push_url  # None means check DB config/env var

    async def load_sources(self):
        """加载数据源配置 - 优先从数据库读取，回退到硬编码"""
        if self.use_db:
            self._load_sources_from_db()
        else:
            self._load_sources_hardcoded()
        logger.info(f"Loaded {len(self.sources)} sources.")

    def _load_sources_from_db(self):
        """从数据库加载活跃的数据源"""
        session = Session()
        try:
            db_sources = SourceManager.get_active(session)
            if not db_sources:
                # 全新部署（数据库为空）时回退到内置源列表，保证健康巡检和
                # 一次性抓取在未做任何数据库配置的情况下也能立即工作。
                logger.info("No active sources in DB, falling back to built-in source list")
                self._load_sources_hardcoded()
                return
            for db_src in db_sources:
                crawler_cls = CRAWLER_MAP.get(db_src.crawler_module)
                if crawler_cls:
                    self.sources[db_src.crawler_module] = crawler_cls()
                else:
                    logger.warning(f"No crawler class found for module: {db_src.crawler_module}")
        finally:
            session.close()

    def _load_sources_hardcoded(self):
        """硬编码加载（向后兼容）"""
        self.sources = {
            "thsnews": ThsnewsCrawler(),
            "aerospace": AerospaceCrawler(),
            "ai_news": AINewsCrawler(),
            "polarizer": PolarizerCrawler(),
            "conflict_events": ConflictEventsCrawler(),
            "financial_markets": FinancialMarketsCrawler(),
            "cls": CLSCrawler(),
            "displaydaily": DisplayDailyCrawler(),
            "spacechina": SpaceChinaCrawler(),
            "space_com": SpaceComCrawler(),
            "nasa": NASACrawler(),
            "the_decoder": TheDecoderCrawler(),
            "synced": SyncedCrawler(),
            "deepmind": DeepMindCrawler(),
            "venturebeat": VentureBeatCrawler(),
            "eu_ai": EUAICrawler(),
            "leiphone": LeiphoneCrawler(),
            "qbitai": QbitaiCrawler(),
            "ofweek": OFweekCrawler(),
            "36kr": Kr36Crawler(),
            "boe": BOECrawler(),
            "spacenews": SpaceNewsCrawler(),
            "aibusiness": AIBusinessCrawler(),
            "lgdisplay": LGDisplayCrawler(),
        }

    async def fetch_all_news(self) -> List[BaseNewsItem]:
        all_news = []

        async def _safe_fetch(name: str, crawler):
            start_time = time.time()
            try:
                logger.info(f"Fetching {name}...")
                async with crawler:
                    # 获取超时配置
                    timeout = 45
                    if self.use_db:
                        session = Session()
                        try:
                            db_src = SourceManager.get_by_module(session, name)
                            if db_src:
                                timeout = db_src.timeout
                        finally:
                            session.close()

                    news = await asyncio.wait_for(crawler.fetch_news(), timeout=timeout)
                    duration = time.time() - start_time
                    logger.info(f"  -> {name} success: {len(news)} items ({duration:.1f}s)")

                    # 保存到数据库
                    if self.use_db:
                        self._save_to_db(name, news, duration)

                    return news
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"  -> {name} failed: {e} ({duration:.1f}s)")

                if self.use_db:
                    self._log_crawl_failure(name, e, duration)

                return []

        tasks = []
        for name, crawler in self.sources.items():
            tasks.append(_safe_fetch(name, crawler))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                all_news.extend(res)

        return all_news

    def _save_to_db(self, source_module: str, news_items: List[BaseNewsItem], duration: float):
        """保存抓取结果到数据库"""
        session = Session()
        try:
            db_src = SourceManager.get_by_module(session, source_module)
            source_id = db_src.id if db_src else None
            source_name = db_src.name if db_src else source_module

            new_count = 0
            for item in news_items:
                # 自动分类
                cat_name = CategoryManager.match(session, item.title, item.summary or '')

                result = ArticleManager.add(
                    session,
                    title=item.title,
                    url=item.url,
                    source_id=source_id,
                    source_name=source_name,
                    summary=item.summary,
                    content=item.content,
                    category=cat_name,
                    severity=item.severity,
                    location=item.location,
                    latitude=item.latitude,
                    longitude=item.longitude,
                    publish_time=item.publish_time,
                )
                if result:
                    new_count += 1

            # 更新源状态
            if db_src:
                SourceManager.update_crawl_status(
                    session, db_src.id, 'success',
                    articles_found=len(news_items), articles_new=new_count
                )

            # 记录日志
            CrawlLogManager.add(
                session, source_id, source_name, 'success',
                articles_found=len(news_items), articles_new=new_count,
                duration_seconds=duration
            )

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB save error: {e}")
        finally:
            session.close()

    def _log_crawl_failure(self, source_module: str, error: Exception, duration: float):
        """记录爬取失败"""
        session = Session()
        try:
            db_src = SourceManager.get_by_module(session, source_module)
            source_id = db_src.id if db_src else None
            source_name = db_src.name if db_src else source_module

            if db_src:
                SourceManager.update_crawl_status(
                    session, db_src.id, 'failed', error_message=str(error)
                )

            CrawlLogManager.add(
                session, source_id, source_name, 'failed',
                error_message=str(error), duration_seconds=duration
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB log error: {e}")
        finally:
            session.close()

    def save_news(self, news_list: List[BaseNewsItem]):
        """保存为 Markdown 报告（向后兼容）"""
        news_dict = [news.to_dict() if isinstance(news, BaseNewsItem) else news for news in news_list]

        # 生成 Markdown 内容
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        md_content = f"""# HS News 抓取报告

**抓取时间**: {timestamp}
**数据源数量**: {len(self.sources)}
**新闻总数**: {len(news_list)}

---

## 📍 新闻明细 (支持地图标点)

"""

        # 排序：按时间倒序（无发布时间的排最后）
        from datetime import datetime as _dt
        news_list.sort(key=lambda x: getattr(x, 'publish_time', None) or _dt.min, reverse=True)

        for news in news_list:
            source = news.source if isinstance(news, BaseNewsItem) else news.get('source', '未知')
            title = news.title if isinstance(news, BaseNewsItem) else news.get('title', '无标题')
            url = news.url if isinstance(news, BaseNewsItem) else news.get('url', '#')
            category = news.category if isinstance(news, BaseNewsItem) else news.get('category', '其他')
            summary = news.summary if isinstance(news, BaseNewsItem) else news.get('summary', '无摘要')
            severity = news.severity if isinstance(news, BaseNewsItem) else news.get('severity', 'low')

            lat = getattr(news, 'latitude', None) or (news.get('latitude') if isinstance(news, dict) else None)
            lng = getattr(news, 'longitude', None) or (news.get('longitude') if isinstance(news, dict) else None)
            location_str = news.location if isinstance(news, BaseNewsItem) else news.get('location', '未知')

            pub_time = "未知"
            if isinstance(news, BaseNewsItem) and news.publish_time:
                pub_time = news.publish_time.strftime('%Y-%m-%d %H:%M')
            elif isinstance(news, dict) and news.get('publishTime'):
                pub_time = news['publishTime']

            md_content += f"### 📰 [{title}]({url})\n\n"
            md_content += f"- **来源**: {source}\n"
            md_content += f"- **分类**: {category}\n"
            md_content += f"- **时间**: {pub_time}\n"
            md_content += f"- **严重程度**: {severity.upper()}\n"

            if lat and lng:
                md_content += f"- **📍 坐标**: `Lat: {lat}, Lng: {lng}` (位置: {location_str})\n"
            else:
                md_content += f"- **📍 坐标**: 缺失 (无法标点)\n"

            md_content += f"\n> **摘要**: {summary}\n\n"
            md_content += "---\n\n"

        # JSON 数据块
        md_content += "<details>\n<summary>📦 点击查看完整 JSON 原始数据 (供内网分析)</summary>\n\n"
        md_content += "```json\n"
        md_content += json.dumps(news_dict, ensure_ascii=False, indent=2)
        md_content += "\n```\n</details>"

        # 写入文件
        output_file = DATA_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"Saved {len(news_dict)} news to {output_file.name}")

    async def run(self):
        """Run a single crawl cycle"""
        logger.info("Starting crawl cycle...")
        news = await self.fetch_all_news()
        self.save_news(news)

        # Push to analyzer
        await self._push_news(news)

        logger.info(f"Cycle completed. Total news: {len(news)}")

    async def _push_news(self, news: List[BaseNewsItem]):
        """Push news to analyzer and mark pushed status"""
        if not self.use_db:
            return

        # Resolve push URL: CLI > env var > DB config
        url = self.push_url or os.environ.get("ANALYZER_URL", "")
        if not url and self.use_db:
            session = Session()
            try:
                url = ConfigManager.get(session, "analyzer_url", "")
            finally:
                session.close()

        if not url:
            return

        pusher = NewsPusher(analyzer_url=url)
        sources = self._get_source_names()
        success = await pusher.push(news, sources)

        if success:
            session = Session()
            try:
                pusher.mark_pushed(session, news)
            finally:
                session.close()

    def _get_source_names(self) -> List[str]:
        """Get human-readable source names"""
        if self.use_db:
            session = Session()
            try:
                active = SourceManager.get_active(session)
                return [s.name for s in active]
            finally:
                session.close()
        return list(self.sources.keys())

    async def run_forever(self, interval_minutes: int = 60):
        """Run cyclically"""
        self.is_running = True
        while self.is_running:
            try:
                await self.run()
                logger.info(f"Sleeping for {interval_minutes} minutes...")
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                self.is_running = False
                logger.info("Stopped by user.")
                break
            except Exception as e:
                logger.error(f"Fatal error in loop: {e}")
                await asyncio.sleep(60)
