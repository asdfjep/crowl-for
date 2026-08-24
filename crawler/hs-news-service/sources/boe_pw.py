"""
京东方 (BOE) 爬虫 - Playwright 版
解决 SSL 错误和 JS 渲染问题
"""
import logging
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightCrawler, NewsItem

logger = logging.getLogger(__name__)


class BOECrawler(PlaywrightCrawler):
    def __init__(self):
        super().__init__(name="boe", base_url="https://www.boe.com", category="polarizer")
        self.url = "https://www.boe.com/cn/newsroom/pressrelease"

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        # 忽略 HTTPS 错误
        # 京东方官网有持续轮询请求，networkidle 永远等不到 → 会卡满 30s 超时。
        # 改为 DOMContentLoaded 后即返回，避免把巡检拖成 error。
        html = await self.fetch_with_browser(self.url, wait_until='domcontentloaded', ignore_https_errors=True)
        if not html:
            return news_list

        try:
            soup = BeautifulSoup(html, 'lxml')
            # 京东方新闻通常在 .news_list li 或 .list-item
            items = soup.select('.news_list li') or soup.select('.list-item') or soup.select('a[href*="/cn/newsroom/"]')
            
            for item in items:
                # 尝试获取链接
                link_elem = item.select_one('a') if item.name != 'a' else item
                if not link_elem:
                    continue
                
                title = link_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                
                if not link or len(title) < 5:
                    continue
                
                if link.startswith('/'):
                    link = f"{self.base_url}{link}"
                elif not link.startswith('http'):
                    continue

                # 尝试解析时间
                time_elem = item.select_one('.time') or item.select_one('.date')
                pub_time = self.now()
                if time_elem:
                    txt = time_elem.get_text(strip=True)
                    try:
                        pub_time = datetime.strptime(txt, '%Y-%m-%d')
                    except:
                        pass

                news_list.append(NewsItem(
                    title=title, url=link, source="京东方",
                    publish_time=pub_time, category="polarizer",
                    summary="", location="中国"
                ))
                if len(news_list) >= 15:
                    break
            
            logger.info(f"京东方: {len(news_list)} 条")
        except Exception as e:
            logger.error(f"京东方 解析失败: {e}")
        
        return news_list

    def now(self):
        from datetime import datetime
        return datetime.now()
