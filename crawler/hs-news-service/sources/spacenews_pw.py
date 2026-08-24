"""
SpaceNews 爬虫 - Playwright 版
解决 429 反爬限制
"""
import re
import logging
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightCrawler, NewsItem

logger = logging.getLogger(__name__)


class SpaceNewsCrawler(PlaywrightCrawler):
    def __init__(self):
        super().__init__(name="spacenews", base_url="https://spacenews.com", category="aerospace")
        self.url = "https://spacenews.com/"

    async def fetch_news(self) -> List[NewsItem]:
        news_list = []
        # SpaceNews 需要较长时间过 Cloudflare 验证
        html = await self.fetch_with_browser(self.url, wait_until='networkidle', timeout=40000)
        if not html:
            return news_list

        try:
            soup = BeautifulSoup(html, 'lxml')
            # 如果页面内容仍然很少，说明被拦截了
            if len(html) < 5000:
                logger.warning(f"SpaceNews 可能被 Cloudflare 拦截 (HTML size: {len(html)})")
                return news_list

            # SpaceNews 文章通常在 article.post 或 h2.entry-title
            items = soup.select('article.post') or soup.select('h2.entry-title a')
            
            seen = set()
            for item in items:
                if item.name == 'h2':
                    link_elem = item.select_one('a')
                else:
                    link_elem = item.select_one('h2 a') or item.select_one('h3 a') or item.select_one('a')

                if not link_elem:
                    continue
                
                title = link_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                
                if not link or len(title) < 5 or link in seen:
                    continue
                seen.add(link)
                
                # 补充完整 URL
                if link.startswith('/'):
                    link = f"{self.base_url}{link}"
                elif not link.startswith('http'):
                    continue

                # 尝试找时间
                time_elem = item.select_one('time') or item.parent.select_one('time')
                pub_time = self.now()
                if time_elem:
                    dt_str = time_elem.get('datetime') or time_elem.get_text(strip=True)
                    try:
                        pub_time = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    except:
                        pass

                news_list.append(NewsItem(
                    title=title, url=link, source="SpaceNews",
                    publish_time=pub_time, category="aerospace",
                    summary="", location="全球"
                ))
                if len(news_list) >= 15:
                    break
            
            logger.info(f"SpaceNews: {len(news_list)} 条")
        except Exception as e:
            logger.error(f"SpaceNews 解析失败: {e}")
        
        return news_list

    def now(self):
        from datetime import datetime
        return datetime.now()
