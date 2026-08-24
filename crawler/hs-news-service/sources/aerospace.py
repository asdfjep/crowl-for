"""
航空航天新闻爬虫
数据源：SpaceFlight Now RSS + 中国航空新闻网
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class AerospaceCrawler(BaseCrawler):
    """航空航天新闻爬虫"""

    def __init__(self):
        super().__init__(
            name="aerospace",
            base_url="https://spaceflightnow.com",
            category="aerospace",
        )
        self.rss_urls = [
            ("https://techcrunch.com/category/space/feed/", "TechCrunch Space"),
            ("https://hnrss.org/frontpage?count=10", "HackerNews"),
        ]

    async def fetch_news(self) -> List[NewsItem]:
        """获取航空航天新闻"""
        all_news = []

        for rss_url, source_name in self.rss_urls:
            try:
                async with self.session.get(rss_url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    text = await response.text()
                    items = self._parse_rss(text, source_name)
                    all_news.extend(items)
            except Exception as e:
                logger.error(f"航空航天 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"航空航天：{len(deduped)} 条")
        return deduped

    def _parse_rss(self, xml_text: str, source_name: str) -> List[NewsItem]:
        """解析 RSS feed"""
        news_list = []
        try:
            root = ElementTree.fromstring(xml_text)
            channel = root.find(".//channel")
            if channel is not None:
                rss_title = channel.findtext("title", "")
                if rss_title:
                    source_name = rss_title

            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", self.base_url)
                description = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")

                if not title or len(title) < 5:
                    continue

                # 清理 HTML 标签
                description = re.sub(r'<[^>]+>', '', description or '').strip()[:300]

                # 解析时间
                publish_time = self._parse_date(pub_date)

                # 航空航天关键词判断
                aerospace_keywords = ["rocket", "launch", "space", "satellite", "NASA", "SpaceX", "orbit", "mission", "航天", "卫星", "火箭", "发射", "太空", "轨道"]
                is_aerospace = any(kw in title.lower() or kw in description.lower() for kw in aerospace_keywords)

                if not is_aerospace:
                    continue

                location = self._extract_location(title + " " + description)

                news_list.append(NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    publish_time=publish_time,
                    category="aerospace",
                    summary=description,
                    location=location,
                ))

                if len(news_list) >= 15:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败: {e}")

        return news_list

    def _parse_date(self, date_str: str) -> datetime:
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S GMT',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%d %H:%M:%S',
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt
            except ValueError:
                continue
        return None

    def _extract_location(self, text: str) -> str:
        """简单提取发射地点"""
        locations = {
            "Florida": "美国，佛罗里达",
            "Cape Canaveral": "美国，卡纳维拉尔角",
            "Kennedy": "美国，肯尼迪航天中心",
            "Vandenberg": "美国，范登堡",
            "China": "中国",
            "Wenchang": "中国，文昌",
            "Xichang": "中国，西昌",
            "Jiuquan": "中国，酒泉",
            "Baikonur": "哈萨克斯坦，拜科努尔",
            "Kourou": "法属圭亚那，库鲁",
            "Tanegashima": "日本，种子岛",
        }
        for keyword, location in locations.items():
            if keyword.lower() in text.lower():
                return location
        return None
