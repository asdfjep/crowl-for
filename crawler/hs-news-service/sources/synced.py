"""
Synced AI 新闻 - RSS (https://syncedreview.com/)
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class SyncedCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(name="synced", base_url="https://syncedreview.com", category="ai")
        self.rss_url = "https://syncedreview.com/feed/"

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        try:
            async with self.session.get(self.rss_url, timeout=self.timeout) as response:
                if response.status != 200:
                    return news_list
                text = await response.text()
                news_list = self._parse_rss(text)
        except Exception as e:
            logger.error(f"Synced 失败: {e}")
        news_list.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"Synced：{len(news_list)} 条")
        return news_list

    def _parse_rss(self, xml_text: str) -> List[NewsItem]:
        news_list = []
        try:
            root = ElementTree.fromstring(xml_text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "")
                description = re.sub(r'<[^>]+>', '', item.findtext("description", "") or '').strip()[:300]
                pub_date = item.findtext("pubDate", "")
                if not title or len(title) < 5:
                    continue
                publish_time = self._parse_date(pub_date)
                news_list.append(NewsItem(
                    title=title, url=link, source="Synced",
                    publish_time=publish_time, category="ai",
                    summary=description, location="全球",
                ))
                if len(news_list) >= 20:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"Synced RSS 解析失败: {e}")
        return news_list

    def _parse_date(self, date_str: str) -> datetime:
        for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                continue
        return None
