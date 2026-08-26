"""
36Kr 爬虫 - Playwright 版
解决 JS 渲染和滑动加载问题
"""
import logging
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightCrawler, NewsItem
from .content_fetch import enrich_items

logger = logging.getLogger(__name__)


class Kr36Crawler(PlaywrightCrawler):
    def __init__(self):
        super().__init__(name="36kr", base_url="https://36kr.com", category="ai")
        self.url = "https://36kr.com/information/web_news"

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        # 36Kr 信息流页面
        html = await self.fetch_with_browser("https://36kr.com/newsflashes", wait_until='networkidle')
        if not html:
            return news_list

        try:
            soup = BeautifulSoup(html, 'lxml')
            # 36Kr 的链接通常在 a[class*=title]
            items = soup.select('a[class*=title]') or soup.select('a[class*=item-title]')
            
            for item in items:
                title = item.get_text(strip=True)
                link = item.get('href', '')
                
                if not link or len(title) < 5:
                    continue
                
                if link.startswith('//'):
                    link = f"https:{link}"
                elif link.startswith('/'):
                    link = f"https://36kr.com{link}"
                elif not link.startswith('http'):
                    continue

                news_list.append(NewsItem(
                    title=title, url=link, source="36Kr",
                    publish_time=self.now(), category="ai",
                    summary="", location="中国"
                ))
                if len(news_list) >= 15:
                    break
            
            logger.info(f"36Kr: {len(news_list)} 条")
        except Exception as e:
            logger.error(f"36Kr 解析失败: {e}")

        # 36kr 文章页是 JS 渲染 + 登录墙，HTTP 抓不到正文：用已装好的 Chromium
        # 并发打开文章页抽取正文（受 18s 预算限制，不会拖超巡检的 30s）。
        await self.enrich_items_with_browser(news_list)
        return news_list

    def now(self):
        from datetime import datetime
        return datetime.now()
