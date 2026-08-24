"""
Space.com 航空航天新闻爬虫
https://www.space.com/
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class SpaceComCrawler(BaseCrawler):
    """Space.com 航空航天新闻"""

    def __init__(self):
        super().__init__(
            name="space_com",
            base_url="https://www.space.com",
            category="aerospace",
        )
        self.rss_url = "https://www.space.com/feeds/all"

    async def fetch_news(self) -> List[NewsItem]:
        """获取 Space.com 新闻"""
        news_list = []
        try:
            async with self.session.get(self.rss_url, timeout=self.timeout) as response:
                if response.status != 200:
                    return news_list
                text = await response.text()
                news_list = self._parse_rss(text)
        except Exception as e:
            logger.error(f"Space.com 失败: {e}")

        news_list.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"Space.com：{len(news_list)} 条")
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
                location = self._extract_location(title + " " + description)

                news_list.append(NewsItem(
                    title=title, url=link, source="Space.com",
                    publish_time=publish_time, category="aerospace",
                    summary=description, location=location,
                ))
                if len(news_list) >= 30:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"Space.com RSS 解析失败: {e}")
        return news_list

    def _parse_date(self, date_str: str) -> datetime:
        for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                continue
        return None

    def _extract_location(self, text: str) -> str:
        locs = {"China": "中国", "Wenchang": "中国，文昌", "Cape Canaveral": "美国，卡纳维拉尔角",
                "Kennedy": "美国，肯尼迪航天中心", "Vandenberg": "美国，范登堡", "Baikonur": "哈萨克斯坦",
                "Mars": "火星", "Moon": "月球", "ISS": "国际空间站"}
        for k, v in locs.items():
            if k in text:
                return v
        return None
