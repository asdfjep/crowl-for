"""
人工智能新闻爬虫
数据源：TechCrunch AI RSS + MIT Technology Review + HackerNews
"""
import re
from datetime import datetime
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class AINewsCrawler(BaseCrawler):
    """人工智能新闻爬虫"""

    def __init__(self):
        super().__init__(
            name="ai_news",
            base_url="https://techcrunch.com",
            category="ai",
        )
        self.rss_urls = [
            ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI"),
            ("https://www.technologyreview.com/feed/", "MIT Tech Review"),
            ("https://hnrss.org/frontpage?count=15", "HackerNews"),
        ]

    async def fetch_news(self) -> List[NewsItem]:
        """获取 AI 新闻"""
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
                logger.error(f"AI 新闻 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"人工智能：{len(deduped)} 条")
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

                # 清理 HTML
                description = re.sub(r'<[^>]+>', '', description or '').strip()[:300]

                publish_time = self._parse_date(pub_date)

                # 检查是否与 AI 相关
                if not self._is_ai_related(title, description):
                    continue

                news_list.append(NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    publish_time=publish_time,
                    category="ai",
                    summary=description,
                    location="全球",
                ))

                if len(news_list) >= 15:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

        return news_list

    def _is_ai_related(self, title: str, description: str) -> bool:
        """判断是否与 AI 相关"""
        text = (title + " " + description).lower()
        ai_keywords = [
            "ai ", " ai,", "ai.",
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "neural network",
            "llm", "gpt", "chatgpt",
            "large language model",
            "generative",
            "openai",
            "anthropic",
            "claude",
            "google ai",
            "transformer",
            "diffusion",
            "autonomous",
            "机器人", "人工智能", "大模型", "深度学习", "机器学习",
            "算法",
        ]
        return any(kw in text for kw in ai_keywords)

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
