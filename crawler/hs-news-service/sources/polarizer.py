"""
偏光片/显示行业新闻爬虫
数据源：OLED-Info RSS + Ars Technica + DisplayDaily 回退
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class PolarizerCrawler(BaseCrawler):
    """偏光片/显示行业新闻爬虫"""

    def __init__(self):
        super().__init__(
            name="polarizer",
            base_url="https://www.oled-info.com",
            category="polarizer",
        )
        self.rss_urls = [
            ("https://www.oled-info.com/rss.xml", "OLED-Info"),
            ("https://arstechnica.com/feed/", "Ars Technica"),
            ("https://www.displaydaily.com/feed/", "DisplayDaily"),
        ]

    async def fetch_news(self) -> List[NewsItem]:
        """获取显示行业新闻"""
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
                logger.error(f"显示行业 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"偏光片/显示：{len(deduped)} 条")
        return deduped

    def _parse_rss(self, xml_text: str, source_name: str) -> List[NewsItem]:
        """解析 RSS feed"""
        news_list = []
        try:
            root = ElementTree.fromstring(xml_text)

            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "")
                description = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")

                if not title or len(title) < 5:
                    continue

                description = re.sub(r'<[^>]+>', '', description or '').strip()[:300]
                publish_time = self._parse_date(pub_date)

                # 检查是否与显示行业相关
                if source_name == "OLED-Info":
                    is_relevant = True  # OLED-Info 全部内容都相关
                else:
                    is_relevant = self._is_display_related(title, description)

                if not is_relevant:
                    continue

                location = self._extract_location(title + " " + description)

                news_list.append(NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    publish_time=publish_time,
                    category="polarizer",
                    summary=description,
                    location=location,
                ))

                if len(news_list) >= 15:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

        return news_list

    def _is_display_related(self, title: str, description: str) -> bool:
        """判断是否与显示行业相关"""
        text = (title + " " + description).lower()
        keywords = [
            "display", "screen", "oled", "lcd", "panel",
            "polarizer", "led", "mini-led", "microled",
            "pixel", "resolution", "4k", "8k",
            "samsung display", "lg display", "boe",
            "偏光片", "显示", "面板", "lcd", "oled",
            "屏幕",
        ]
        return any(kw in text for kw in keywords)

    def _extract_location(self, text: str) -> str:
        locations = {
            "korea": "韩国",
            "china": "中国",
            "japan": "日本",
            "taiwan": "台湾",
            "usa": "美国",
            "samsung": "韩国，三星",
            "lg": "韩国，LG",
            "boe": "中国，京东方",
        }
        for keyword, location in locations.items():
            if keyword.lower() in text.lower():
                return location
        return None

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
