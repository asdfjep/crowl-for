"""
News Push Service - 将爬取的新闻推送到分析服务
"""
import aiohttp
import asyncio
import logging
from typing import List, Optional
from sources.base import NewsItem as BaseNewsItem

logger = logging.getLogger(__name__)

PUSH_TIMEOUT = aiohttp.ClientTimeout(total=60)


class NewsPusher:
    """推送新闻到分析服务"""

    def __init__(self, analyzer_url: str):
        self.analyzer_url = analyzer_url

    async def push(self, news_items: List[BaseNewsItem], sources: List[str]) -> bool:
        """
        推送新闻到分析器
        返回 True 表示成功，False 表示失败（不抛异常）
        """
        if not news_items:
            logger.info("No news to push")
            return True

        payload = {
            "news": [item.to_dict() for item in news_items],
            "sources": sources,
            "save_json": True,
        }

        try:
            async with aiohttp.ClientSession(timeout=PUSH_TIMEOUT) as session:
                async with session.post(
                    self.analyzer_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        summary = data.get("summary", {})
                        logger.info(
                            f"Push success: {summary.get('unique_count', 0)} unique, "
                            f"{summary.get('cluster_count', 0)} clusters, "
                            f"report: {data.get('report_path', 'N/A')}"
                        )
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"Push failed: HTTP {resp.status} - {body[:200]}")
                        return False

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Cannot connect to analyzer at {self.analyzer_url}: {e}")
            return False
        except asyncio.TimeoutError:
            logger.error(f"Push timed out after {PUSH_TIMEOUT.total}s")
            return False
        except Exception as e:
            logger.error(f"Push error: {e}")
            return False

    def mark_pushed(self, session, news_items: List[BaseNewsItem]) -> int:
        """
        将已推送的文章在 DB 中标记 is_pushed = True
        通过 URL 匹配（Article.url 有 unique 约束）
        """
        from app.models import Article

        count = 0
        for item in news_items:
            article = session.query(Article).filter_by(url=item.url).first()
            if article and not article.is_pushed:
                article.is_pushed = True
                count += 1

        if count > 0:
            session.commit()
            logger.info(f"Marked {count} articles as pushed")
        return count
