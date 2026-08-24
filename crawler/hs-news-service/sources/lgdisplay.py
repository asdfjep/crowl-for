"""
LG Display 新闻爬虫 - HTML 解析
https://www.lgdisplay.com/
无 RSS，使用 HTML 解析
"""
import re
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .base import BaseCrawler, NewsItem, logger


class LGDisplayCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(name="lgdisplay", base_url="https://www.lgdisplay.com", category="polarizer")

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        try:
            # Try multiple URLs
            urls = [
                f"{self.base_url}/en/press/news",
                f"{self.base_url}/en/about/news",
                f"{self.base_url}/en/press/press-releases",
            ]
            for url in urls:
                async with self.session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    html = await response.text()
                    news_list = self._parse_html(html, url)
                    if news_list:
                        break
        except Exception as e:
            logger.error(f"LG Display 失败: {e}")
        news_list.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"LG Display：{len(news_list)} 条")
        return news_list

    def _parse_html(self, html: str, source_url: str) -> List[NewsItem]:
        news_list = []
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Look for news list items
            items = (soup.select('.news-list li') or soup.select('.press-list li') or
                     soup.select('.news-item') or soup.select('.list-item') or
                     soup.select('table tr') or soup.select('.news-card'))

            for item in items[:30]:
                link = item.select_one('a')
                if not link:
                    continue
                title = link.get_text(strip=True)
                url = link.get('href', '')
                if not url or len(title) < 5:
                    continue
                if url.startswith('/'):
                    url = f"{self.base_url}{url}"
                elif not url.startswith('http'):
                    url = f"{self.base_url}/{url}"

                # Try to find date
                time_elem = item.select_one('time') or item.select_one('.date') or item.select_one('.news-date')
                publish_time = None
                if time_elem:
                    text = time_elem.get_text(strip=True)
                    for fmt in ['%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%d %B %Y']:
                        try:
                            publish_time = datetime.strptime(text, fmt)
                            break
                        except ValueError:
                            continue

                news_list.append(NewsItem(
                    title=title, url=url, source="LG Display",
                    publish_time=publish_time, category="polarizer",
                    summary="", location="韩国",
                ))
                if len(news_list) >= 20:
                    break

            # Fallback: find all links that look like news
            if not news_list:
                links = soup.select('a[href*="/news/"], a[href*="/press/"]')
                seen = set()
                for a in links[:30]:
                    title = a.get_text(strip=True)
                    url = a.get('href', '')
                    if not url or len(title) < 10:
                        continue
                    if url.startswith('/'):
                        url = f"{self.base_url}{url}"
                    elif not url.startswith('http'):
                        continue
                    if url in seen:
                        continue
                    seen.add(url)
                    news_list.append(NewsItem(
                        title=title, url=url, source="LG Display",
                        publish_time=None, category="polarizer",
                        summary="", location="韩国",
                    ))
                    if len(news_list) >= 15:
                        break

        except Exception as e:
            logger.error(f"LG Display HTML 解析失败: {e}")
        return news_list
