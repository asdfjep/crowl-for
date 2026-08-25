"""
可替换数据源：用服务器可达的公开 RSS/Atom Feed 补充/替换抓不到的站点。

同一台服务器上某些站点不可达/被反爬（如 TheVerge、SpaceNews、BOE、LG Display、
AIBusiness），用这些稳定、公开的 Feed 按主题补齐内容。health check 会如实反馈每个
Feed 是否可用，若个别仍不可达，只需从 EXTRA_FEEDS 里移除该条即可，无需改代码。
"""
import re
from datetime import datetime
from typing import Dict, List
from xml.etree import ElementTree

from .base import BaseCrawler, NewsItem, logger

EXTRA_FEEDS = [
    # 商业航天
    {"key": "ars_science", "name": "Ars Technica Science",
     "url": "https://arstechnica.com/science/feed/", "category": "aerospace"},
    {"key": "techcrunch_space", "name": "TechCrunch Space",
     "url": "https://techcrunch.com/category/space/feed/", "category": "aerospace"},
    {"key": "nasa_brief", "name": "NASA Breaking News",
     "url": "https://www.nasa.gov/feed/", "category": "aerospace"},
    # 人工智能
    {"key": "arxiv_ai", "name": "arXiv cs.AI",
     "url": "https://export.arxiv.org/rss/cs.AI", "category": "ai"},
    {"key": "hf_blog", "name": "Hugging Face Blog",
     "url": "https://huggingface.co/blog/feed.xml", "category": "ai"},
    # 偏光板 / 显示
    {"key": "displaydaily", "name": "Display Daily",
     "url": "https://www.displaydaily.com/feed", "category": "polarizer"},
    {"key": "flatpanelshd", "name": "FlatPanelsHD",
     "url": "https://www.flatpanelshd.com/flatpanelshd_rss.xml", "category": "polarizer"},
]


def _localname(tag: str) -> str:
    """去掉 XML 命名空间，得到标签本地名（兼容 RSS <item> 与 Atom <entry>）。"""
    return tag.rsplit("}", 1)[-1]


class GenericRSSFeedCrawler(BaseCrawler):
    """抓取一个 RSS/Atom Feed 的通用爬虫。"""

    def __init__(self, key: str, name: str, url: str, category: str):
        super().__init__(name=name, base_url=url, category=category)
        self.key = key
        self.feed_url = url

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        try:
            async with self.session.get(self.feed_url, timeout=self.timeout) as response:
                if response.status != 200:
                    logger.info("[%s] %s -> HTTP %s", self.key, self.feed_url, response.status)
                    return news_list
                text = await response.text()
                news_list = self._parse_feed(text)
        except Exception as exc:
            logger.error("[%s] %s 失败: %s", self.key, self.feed_url, exc)
        news_list.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        return news_list[:20]

    def _parse_feed(self, text: str) -> List[NewsItem]:
        out = []
        try:
            root = ElementTree.fromstring(text)
            items = [el for el in root.iter() if _localname(el.tag) in ("item", "entry")]
            for el in items:
                fields = {}
                link = ""
                for child in el:
                    name = _localname(child.tag)
                    if name == "link":
                        link = child.text or (child.get("href") or "")
                    elif name in fields:
                        continue
                    else:
                        fields[name] = child.text or ""
                title = (fields.get("title") or "").strip()
                if not title or len(title) < 5:
                    continue
                description = re.sub(r"<[^>]+>", "", fields.get("description") or fields.get("summary") or "").strip()[:300]
                pub = (fields.get("pubDate") or fields.get("published") or fields.get("updated")
                       or fields.get("date") or "")
                link = (link or "").strip()
                if not link.startswith("http"):
                    continue
                out.append(NewsItem(
                    title=title,
                    url=link,
                    source=self.name,
                    publish_time=self._parse_date(pub),
                    category=self.category,
                    summary=description,
                    location="全球",
                ))
        except ElementTree.ParseError as exc:
            logger.error("[%s] Feed 解析失败: %s", self.key, exc)
        return out

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return None
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                continue
        return None


def build_crawlers() -> Dict[str, GenericRSSFeedCrawler]:
    return {
        item["key"]: GenericRSSFeedCrawler(item["key"], item["name"], item["url"], item["category"])
        for item in EXTRA_FEEDS
    }


EXTRA_CRAWLERS = build_crawlers()