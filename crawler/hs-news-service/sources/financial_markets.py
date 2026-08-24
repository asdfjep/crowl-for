"""
金融市场监控爬虫
数据源：同花顺财经 API + TechCrunch + HackerNews
"""
import re
from datetime import datetime, timedelta
from typing import List
from xml.etree import ElementTree
from .base import BaseCrawler, NewsItem, logger


class FinancialMarketsCrawler(BaseCrawler):
    """金融市场爬虫"""

    def __init__(self):
        super().__init__(
            name="financial_markets",
            base_url="https://news.10jqka.com.cn",
            category="economy",
        )
        self.rss_urls = [
            ("https://hnrss.org/frontpage?count=15", "HackerNews"),
            ("https://techcrunch.com/feed/", "TechCrunch"),
        ]

    async def fetch_news(self) -> List[NewsItem]:
        """获取金融市场新闻"""
        all_news = []

        # 1. 同花顺财经 API
        all_news.extend(await self._fetch_ths_finance())

        # 2. RSS 源筛选财经/商业相关内容
        for rss_url, source_name in self.rss_urls:
            try:
                async with self.session.get(rss_url, timeout=self.timeout) as response:
                    if response.status != 200:
                        continue
                    text = await response.text()
                    items = self._parse_rss(text, source_name)
                    all_news.extend(items)
            except Exception as e:
                logger.error(f"金融新闻 RSS 失败 {rss_url}: {e}")

        # 去重
        seen = set()
        deduped = []
        for n in all_news:
            key = n.title.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)

        deduped.sort(key=lambda x: x.publish_time or datetime.min, reverse=True)
        logger.info(f"金融市场：{len(deduped)} 条")
        return deduped

    async def _fetch_ths_finance(self) -> List[NewsItem]:
        """从同花顺获取财经新闻"""
        news_list = []
        api_url = f"{self.base_url}/tapp/news/push/stock/?page=1&tag=&track=website&order=hot&pagesize=15"
        try:
            async with self.session.get(api_url, timeout=self.timeout) as response:
                if response.status != 200:
                    return news_list
                data = await response.json()
                if data.get("code") != "200":
                    return news_list
                items = data.get("data", {}).get("list", [])
                for item in items:
                    title = item.get("title", "").strip()
                    summary = item.get("digest", "") or item.get("short", "")
                    url = item.get("url", "")
                    ts = item.get("ctime", 0)
                    tag = item.get("tag", "")

                    if not title or len(title) < 3:
                        continue

                    try:
                        publish_time = datetime.fromtimestamp(int(ts))
                    except Exception:
                        publish_time = None

                    news_list.append(NewsItem(
                        title=title,
                        url=url,
                        source="同花顺财经",
                        publish_time=publish_time,
                        category="economy",
                        summary=summary,
                        location="中国",
                        tags=[tag] if tag else [],
                    ))
        except Exception as e:
            logger.error(f"同花顺财经请求失败：{e}")

        return news_list

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

                # 筛选财经/商业相关
                if not self._is_finance_related(title, description):
                    continue

                news_list.append(NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    publish_time=publish_time,
                    category="economy",
                    summary=description,
                    location="全球",
                ))

                if len(news_list) >= 10:
                    break
        except ElementTree.ParseError as e:
            logger.error(f"RSS 解析失败 {source_name}: {e}")

        return news_list

    def _is_finance_related(self, title: str, description: str) -> bool:
        """判断是否与财经相关"""
        text = (title + " " + description).lower()
        keywords = [
            "stock", "market", "finance", "economic", "fund",
            "ipo", "revenue", "earnings", "acquisition", "startup",
            "funding", "invest", "valuation", "crypto", "bitcoin",
            "fed", "interest rate", "inflation",
            "股票", "市场", "金融", "经济", "基金",
            "投资", "上市", "融资", "估值",
            "加息", "降息", "通胀",
        ]
        return any(kw in text for kw in keywords)

    def _generate_market_news(self) -> List[NewsItem]:
        """生成市场动态（回退方案）"""
        events = [
            {
                "title": "亚太股市今日表现分化",
                "summary": "日经指数小幅上涨，恒生指数震荡整理",
                "location": "亚太",
            },
            {
                "title": "科技股持续关注 AI 投资回报",
                "summary": "大型科技公司面临 AI 基础设施投资回报压力",
                "location": "美国",
            },
            {
                "title": "大宗商品价格波动加剧",
                "summary": "原油和贵金属价格出现较大波动",
                "location": "全球",
            },
        ]

        news_list = []
        for i, event in enumerate(events):
            news_list.append(NewsItem(
                title=event["title"],
                url=f"{self.base_url}/market/{i}",
                source="HS News 市场监测",
                publish_time=datetime.now() - timedelta(hours=i * 3),
                category="economy",
                summary=event["summary"],
                location=event["location"],
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
                # 统一转为 naive datetime（去掉时区信息）避免排序比较错误
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt
            except ValueError:
                continue
        return None
