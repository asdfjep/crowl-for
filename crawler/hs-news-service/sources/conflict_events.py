"""
冲突事件监测爬虫
数据源：多源 RSS 筛选军事/冲突相关内容
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class ConflictEventsCrawler(BaseCrawler):
    """冲突事件爬虫"""

    def __init__(self):
        super().__init__(
            name="conflict_events",
            base_url="https://www.theverge.com",
            category="military",
        )
        self.rss_urls = [
            ("https://www.theverge.com/rss/index.xml", "The Verge"),
            ("https://hnrss.org/frontpage?count=20", "HackerNews"),
        ]

    async def fetch_news(self) -> List[NewsItem]:
        """获取冲突/军事事件"""
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
                logger.error(f"冲突事件 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"冲突事件：{len(deduped)} 条")
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

                # 筛选军事/冲突相关
                if not self._is_conflict_related(title, description):
                    continue

                location = self._extract_location(title + " " + description)

                news_list.append(NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    publish_time=publish_time,
                    category="military",
                    summary=description,
                    location=location,
                ))

                if len(news_list) >= 10:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

        return news_list

    def _is_conflict_related(self, title: str, description: str) -> bool:
        """判断是否与冲突/军事相关"""
        text = (title + " " + description).lower()
        keywords = [
            "war", "conflict", "military", "attack", "defense",
            "sanction", "troop", "missile", "drone",
            "cyber attack", "hacking", "security breach",
            "战争", "冲突", "军事", "袭击", "防御",
            "制裁", "军队", "导弹", "无人机",
            "网络攻击", "黑客",
        ]
        return any(kw in text for kw in keywords)

    def _extract_location(self, text: str) -> str:
        locations = {
            "ukraine": "乌克兰",
            "russia": "俄罗斯",
            "israel": "以色列",
            "palestine": "巴勒斯坦",
            "gaza": "加沙",
            "syria": "叙利亚",
            "iran": "伊朗",
            "china": "中国",
            "taiwan": "台湾",
            "south china sea": "南海",
            "north korea": "朝鲜",
            "yemen": "也门",
            "afghanistan": "阿富汗",
            "myanmar": "缅甸",
        }
        for keyword, location in locations.items():
            if keyword.lower() in text.lower():
                return location
        return None

    def _generate_events(self) -> List[NewsItem]:
        """生成实时日期的事件（回退方案）"""
        from datetime import timedelta
        events = [
            {
                "title": "全球网络安全事件持续升级",
                "location": "全球",
                "latitude": 0.0,
                "longitude": 0.0,
                "summary": "多国报告网络攻击事件增加，网络安全形势趋紧",
            },
            {
                "title": "中东地区紧张局势持续",
                "location": "中东",
                "latitude": 25.0,
                "longitude": 45.0,
                "summary": "地区局势持续紧张，各方保持军事警戒",
            },
            {
                "title": "亚太地区军事演习常态化",
                "location": "亚太",
                "latitude": 20.0,
                "longitude": 120.0,
                "summary": "多国在亚太地区举行联合军事演习",
            },
        ]

        news_list = []
        for i, event in enumerate(events):
            news_list.append(NewsItem(
                title=event["title"],
                url=f"{self.base_url}/conflict/{i}",
                source="HS News 监测",
                publish_time=datetime.now() - timedelta(hours=i * 4),
                category="military",
                summary=event["summary"],
                location=event["location"],
                latitude=event["latitude"],
                longitude=event["longitude"],
            ))

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
