"""
AI Business 新闻爬虫 - HTML 解析
https://aibusiness.com/
无 RSS，使用 HTML 解析
"""
import re
import json
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .base import BaseCrawler, NewsItem, logger


class AIBusinessCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(name="aibusiness", base_url="https://aibusiness.com", category="ai")

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        try:
            async with self.session.get(self.base_url, timeout=self.timeout) as response:
                if response.status != 200:
                    return news_list
                html = await response.text()
                news_list = self._parse_html(html)
        except Exception as e:
            logger.error(f"AI Business 失败: {e}")
        news_list.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"AI Business：{len(news_list)} 条")
        return news_list

    def _parse_html(self, html: str) -> List[NewsItem]:
        news_list = []
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Try to find article cards
            articles = soup.select('article') or soup.select('.post') or soup.select('.card')

            if not articles:
                # Fallback: look for JSON-LD or meta tags
                # Try finding links in nav/main
                links = soup.select('a[href*="/news/"], a[href*="/ai/"], a[href*="/article/"]')
                seen = set()
                for a in links[:30]:
                    title = a.get_text(strip=True)
                    url = a.get('href', '')
                    if not url:
                        continue
                    if url.startswith('/'):
                        url = f"{self.base_url}{url}"
                    elif not url.startswith('http'):
                        continue
                    if url in seen or len(title) < 10:
                        continue
                    seen.add(url)
                    news_list.append(NewsItem(
                        title=title, url=url, source="AI Business",
                        publish_time=None, category="ai",
                        summary="", location="全球",
                    ))
                    if len(news_list) >= 20:
                        break

            for article in articles[:30]:
                title_elem = article.select_one('h2 a') or article.select_one('h3 a') or article.select_one('a[rel="bookmark"]')
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                url = title_elem.get('href', '')
                if not url or len(title) < 5:
                    continue
                if url.startswith('/'):
                    url = f"{self.base_url}{url}"
                elif not url.startswith('http'):
                    continue

                summary_elem = article.select_one('.excerpt') or article.select_one('.summary') or article.select_one('p')
                summary = summary_elem.get_text(strip=True)[:300] if summary_elem else ''

                time_elem = article.select_one('time')
                publish_time = None
                if time_elem:
                    dt_attr = time_elem.get('datetime')
                    if dt_attr:
                        try:
                            publish_time = datetime.fromisoformat(dt_attr.replace('Z', '+00:00'))
                            if publish_time.tzinfo:
                                publish_time = publish_time.replace(tzinfo=None)
                        except:
                            pass

                news_list.append(NewsItem(
                    title=title, url=url, source="AI Business",
                    publish_time=publish_time, category="ai",
                    summary=summary, location="全球",
                ))
                if len(news_list) >= 20:
                    break
        except Exception as e:
            logger.error(f"AI Business HTML 解析失败: {e}")
        return news_list
