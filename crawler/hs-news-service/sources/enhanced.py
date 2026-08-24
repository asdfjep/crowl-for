"""
HS News - 增强的爬虫模块
整合专业财经/航天新闻源
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from xml.etree import ElementTree

from sources.base import NewsItem, BaseCrawler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CLSCrawler(BaseCrawler):
    """财联社 / 新浪财经 - 财经新闻爬虫
    注：财联社 API 有签名保护，使用新浪财经 API 替代
    """

    def __init__(self):
        super().__init__(
            name="cls",
            base_url="https://finance.sina.com.cn",
            category="economy",
        )

    async def fetch_news(self) -> List[NewsItem]:
        """通过新浪财经 API 获取财经新闻"""
        news_list = []

        api_urls = [
            # 综合财经
            "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=20&page=1",
            # 国际财经
            "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2521&k=&num=15&page=1",
        ]

        for api_url in api_urls:
            try:
                async with self.session.get(api_url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    text = await response.text()
                    # API 可能返回 JSONP (callback({...}))
                    text = text.strip()
                    if text.startswith("callback("):
                        text = text[len("callback("):-1]
                    elif text.startswith("var data = "):
                        text = text[len("var data = "):]

                    data = await response.json() if False else __import__("json").loads(text)

                    items = data.get("result", {}).get("data", [])
                    for item in items:
                        news = self._parse_item(item)
                        if news:
                            news_list.append(news)
            except Exception as e:
                logger.error(f"新浪财经 API 失败：{e}")

        # 去重
        seen = set()
        deduped = []
        for n in news_list:
            if n.url not in seen:
                seen.add(n.url)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"财联社/新浪财经：{len(deduped)} 条")
        return deduped

    def _parse_item(self, item: dict) -> NewsItem:
        """解析新浪财经新闻项"""
        try:
            title = item.get("title", "").strip()
            summary = item.get("intro", "") or item.get("summary", "")
            url = item.get("url", "")
            ctime = item.get("ctime", 0)

            if not title or len(title) < 3 or not url:
                return None

            try:
                publish_time = datetime.fromtimestamp(int(ctime))
            except Exception:
                publish_time = None

            category = self.parse_category(title, summary)

            return NewsItem(
                title=title,
                url=url,
                source="新浪财经",
                publish_time=publish_time,
                category=category,
                summary=summary,
                location="中国",
            )
        except Exception as e:
            logger.error(f"解析新浪财经项失败：{e}")
            return None


class DisplayDailyCrawler(BaseCrawler):
    """显示行业新闻爬虫
    数据源：OLED-Info + Ars Technica (筛选显示相关)
    """

    def __init__(self):
        super().__init__(
            name="displaydaily",
            base_url="https://www.oled-info.com",
            category="polarizer",
        )

    async def fetch_news(self) -> List[NewsItem]:
        """获取显示行业新闻"""
        all_news = []

        # OLED-Info RSS (专门覆盖显示行业)
        for rss_url, source_name in [
            ("https://www.oled-info.com/rss.xml", "OLED-Info"),
            ("https://arstechnica.com/gadgets/feed/", "Ars Technica Gadgets"),
        ]:
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
        logger.info(f"显示行业/Daily：{len(deduped)} 条")
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

                # 显示行业关键词
                text = (title + " " + description).lower()
                display_keywords = [
                    "display", "oled", "lcd", "panel", "screen",
                    "polarizer", "led", "mini-led", "microled",
                    "pixel", "resolution", "samsung display",
                    "lg display", "boe", "tcl", "sharp",
                    "显示", "面板", "oled", "lcd", "屏幕",
                    "偏光片",
                ]

                is_relevant = any(kw in text for kw in display_keywords)

                # OLED-Info 全部内容都相关
                if source_name == "OLED-Info" or is_relevant:
                    news_list.append(NewsItem(
                        title=title,
                        url=link,
                        source=source_name,
                        publish_time=publish_time,
                        category="polarizer",
                        summary=description,
                        location="全球",
                    ))

                if len(news_list) >= 15:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

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


class SpaceChinaCrawler(BaseCrawler):
    """中国航天科技集团爬虫
    数据源：NASA RSS + SpaceNews RSS + SpaceFlight Now RSS
    """

    def __init__(self):
        super().__init__(
            name="spacechina",
            base_url="https://spacenews.com",
            category="aerospace",
        )

    async def fetch_news(self) -> List[NewsItem]:
        """获取航天新闻"""
        all_news = []

        for rss_url, source_name in [
            ("https://techcrunch.com/category/space/feed/", "TechCrunch Space"),
            ("https://hnrss.org/frontpage?count=10", "HackerNews"),
        ]:
            try:
                async with self.session.get(rss_url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    text = await response.text()
                    items = self._parse_rss(text, source_name)
                    all_news.extend(items)
            except Exception as e:
                logger.error(f"航天 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"航天科技/SpaceNews：{len(deduped)} 条")
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

                if len(news_list) >= 20:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

        return news_list

    def _extract_location(self, text: str) -> str:
        locations = {
            "China": "中国",
            "Wenchang": "中国，文昌",
            "Xichang": "中国，西昌",
            "Jiuquan": "中国，酒泉",
            "Taiyuan": "中国，太原",
            "Cape Canaveral": "美国，卡纳维拉尔角",
            "Kennedy": "美国，肯尼迪航天中心",
            "Vandenberg": "美国，范登堡",
            "Baikonur": "哈萨克斯坦，拜科努尔",
            "Kourou": "法属圭亚那，库鲁",
            "Tanegashima": "日本，种子岛",
        }
        for keyword, location in locations.items():
            if keyword in text:
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
