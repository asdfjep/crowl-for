"""
同花顺新闻爬虫 - 使用官方 API + 详情页抓取
"""
import asyncio
import json
import time
from datetime import datetime
from typing import List
from pathlib import Path
from bs4 import BeautifulSoup
from .base import BaseCrawler, NewsItem, logger


class ThsnewsCrawler(BaseCrawler):
    """同花顺新闻爬虫"""

    def __init__(self):
        super().__init__(
            name="thsnews",
            base_url="https://news.10jqka.com.cn",
            category="economy",
        )

    async def fetch_news(self) -> List[NewsItem]:
        """通过同花顺 API 获取新闻，并对摘要过短的文章抓取详情页"""
        news_list = []

        api_urls = [
            f"{self.base_url}/tapp/news/push/stock/?page=1&tag=&track=website&order=hot&pagesize=20",
        ]

        for api_url in api_urls:
            try:
                async with self.session.get(api_url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()
                    if data.get("code") != "200":
                        continue
                    items = data.get("data", {}).get("list", [])
                    for item in items:
                        news = self._parse_item(item)
                        if news:
                            news_list.append(news)
            except Exception as e:
                logger.error(f"同花顺 API 请求失败：{e}")

        # 去重（按 URL）
        seen = set()
        deduped = []
        for n in news_list:
            if n.url not in seen:
                seen.add(n.url)
                deduped.append(n)

        # 摘要增强：对摘要过短的文章抓取详情页
        deduped = await self._enrich_summaries(deduped)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"同花顺：{len(deduped)} 条")
        return deduped

    async def _enrich_summaries(self, news_list: List[NewsItem]) -> List[NewsItem]:
        """对摘要过短（<50字）的文章抓取详情页"""
        short_news = [n for n in news_list if n.summary and len(n.summary) < 50]
        if not short_news:
            return news_list

        logger.info(f"同花顺：抓取 {len(short_news)} 篇详情页")
        sem = asyncio.Semaphore(5)

        async def bounded_fetch(n):
            async with sem:
                return await self._fetch_detail(n)

        await asyncio.gather(*[bounded_fetch(n) for n in short_news], return_exceptions=True)

        return news_list

    async def _fetch_detail(self, news: NewsItem) -> bool:
        """抓取文章详情页，提取摘要/正文"""
        if not news.url:
            return False
        try:
            async with self.session.get(news.url, timeout=self.timeout) as response:
                if response.status != 200:
                    return False
                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')

                # 同花顺详情页：摘要通常在 meta description 或 .titTop 中
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc and meta_desc.get('content'):
                    desc = meta_desc['content'].strip()
                    if desc and len(desc) > len(news.summary or ''):
                        news.summary = desc[:300]
                        return True

                # 备用：提取 .conMain 或 .article 中的正文
                article = soup.select_one('.conMain') or soup.select_one('.article') or soup.select_one('.detail_con')
                if article:
                    text = article.get_text(strip=True)
                    if text and len(text) > len(news.summary or ''):
                        news.summary = text[:300]
                        return True

                return False
        except Exception as e:
            logger.debug(f"同花顺详情页抓取失败 {news.url}: {e}")
            return False

    def _parse_item(self, item: dict) -> NewsItem:
        """解析单条新闻"""
        try:
            title = item.get("title", "").strip()
            summary = item.get("digest", "") or item.get("short", "")
            url = item.get("url", "")
            tag = item.get("tag", "")
            ts = item.get("ctime", 0)

            if not title or len(title) < 3:
                return None

            try:
                publish_time = datetime.fromtimestamp(int(ts))
            except Exception:
                publish_time = None

            category = self.parse_category(title, summary)

            return NewsItem(
                title=title,
                url=url,
                source="同花顺",
                publish_time=publish_time,
                category=category,
                summary=summary,
                location="中国",
                tags=[tag] if tag else [],
            )
        except Exception as e:
            logger.error(f"解析同花顺新闻项失败：{e}")
            return None
