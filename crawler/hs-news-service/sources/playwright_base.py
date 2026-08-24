"""
基于 Playwright 的高级爬虫基类
用于解决 JS 渲染、反爬保护、SSL 错误等问题
"""
import asyncio
import logging
from typing import List, Optional
from playwright.async_api import async_playwright, Page, Browser
from .base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class PlaywrightCrawler(BaseCrawler):
    """使用真实浏览器内核的爬虫基类"""

    # 子类可覆盖的配置
    # 浏览器启动参数
    browser_args = [
        '--disable-blink-features=AutomationControlled', # 隐藏自动化特征
        '--no-sandbox', # WSL/Linux 必需
        '--disable-dev-shm-usage', # 防止共享内存溢出
    ]

    # 反爬检测规避脚本
    stealth_script = """
        () => {
            // 隐藏 webdriver 属性
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // 修改插件数量
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            // 修改语言
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            // 修改平台
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        }
    """

    async def fetch_with_browser(
        self,
        url: str,
        wait_until: str = 'domcontentloaded',
        timeout: float = 30000,
        ignore_https_errors: bool = True,
        headless: bool = True
    ) -> Optional[str]:
        """
        启动浏览器获取页面 HTML
        """
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=self.browser_args
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    ignore_https_errors=ignore_https_errors,
                    locale="zh-CN"
                )
                page = await context.new_page()
                
                # 注入反规避脚本
                await page.add_init_script(self.stealth_script)

                # 访问页面
                await page.goto(url, wait_until=wait_until, timeout=timeout)
                
                # 额外等待一小段时间让动态内容加载
                await asyncio.sleep(2)

                html = await page.content()
                await browser.close()
                return html

            except Exception as e:
                logger.error(f"Playwright 访问失败 {url}: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    async def extract_links_with_browser(
        self,
        url: str,
        selectors: List[str],
        **kwargs
    ) -> List[NewsItem]:
        """
        通用链接提取方法
        """
        html = await self.fetch_with_browser(url, **kwargs)
        if not html:
            return []
        return self.parse_links_from_html(html)

    def parse_links_from_html(self, html: str) -> List[NewsItem]:
        """
        从 HTML 中解析新闻项 (子类需实现具体逻辑，这里提供通用模板)
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        news_list = []
        # 默认尝试寻找文章列表
        items = soup.select('article') or soup.select('.news-list li') or soup.select('.post')
        for item in items[:20]:
            title_elem = item.select_one('h2 a') or item.select_one('h3 a') or item.select_one('a')
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            link = title_elem.get('href', '')
            if title and link and len(title) > 5:
                news_list.append(NewsItem(
                    title=title, url=link, source=self.name,
                    publish_time=self.now(), category=self.category,
                    location="全球"
                ))
        return news_list

    def now(self):
        from datetime import datetime
        return datetime.now()
