"""
OFweek 显示网爬虫 - Playwright 版
解决 JS 渲染问题
"""
import logging
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightCrawler, NewsItem
from .content_fetch import enrich_items

logger = logging.getLogger(__name__)


class OFweekCrawler(PlaywrightCrawler):
    def __init__(self):
        super().__init__(name="ofweek_display", base_url="https://display.ofweek.com", category="polarizer")
        self.url = "https://display.ofweek.com/"

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        html = await self.fetch_with_browser(self.url, wait_until='networkidle')
        if not html:
            return news_list

        try:
            soup = BeautifulSoup(html, 'lxml')
            # OFweek 列表通常在 .artList li 或 .news_list li
            items = soup.select('.artList li') or soup.select('.list li') or soup.select('.news-item')
            
            for item in items:
                link_elem = item.select_one('a')
                if not link_elem:
                    continue
                title = link_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                
                if not link or len(title) < 5:
                    continue
                
                if link.startswith('/'):
                    link = f"https://display.ofweek.com{link}"
                elif not link.startswith('http'):
                    continue

                # 时间
                time_elem = item.select_one('.time') or item.select_one('.date')
                pub_time = self.now()
                if time_elem:
                    time_text = time_elem.get_text(strip=True)
                    for fmt in ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d']:
                        try:
                            pub_time = datetime.strptime(time_text, fmt)
                            break
                        except:
                            continue

                # 提取摘要 (尝试寻找 .summary 或 p 标签)
                summary = ""
                summary_elem = item.select_one('.summary') or item.select_one('p')
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)[:200]

                # 提取地点 (简单关键词匹配)
                location = self._extract_location(title + " " + summary)

                news_list.append(NewsItem(
                    title=title, url=link, source="OFweek",
                    publish_time=pub_time, category="polarizer",
                    summary=summary, location=location,
                    # 默认给个中心坐标，如果有具体地点再精细化（这里先给通用）
                    latitude=None, longitude=None 
                ))
                if len(news_list) >= 15:
                    break
            
            logger.info(f"OFweek: {len(news_list)} 条")
        except Exception as e:
            logger.error(f"OFweek 解析失败: {e}")

        await enrich_items(self, news_list, limit=8)
        return news_list

    def _extract_location(self, text: str) -> str:
        """简单提取地点关键词"""
        locs = {
            "中国": (35.8617, 104.1954),
            "深圳": (22.543, 114.058),
            "北京": (39.9042, 116.4074),
            "上海": (31.2304, 121.4737),
            "美国": (37.0902, -95.7129),
            "韩国": (35.9078, 127.7669),
            "日本": (36.2048, 138.2529),
        }
        for loc, (lat, lng) in locs.items():
            if loc in text:
                # 如果能匹配到具体城市，可以返回更精确的
                # 这里简化处理，返回地点名
                return loc
        return None

    def now(self):
        from datetime import datetime
        return datetime.now()
