"""
Generic article-body extraction used to enrich title-only crawler items.

Most listing/feed crawlers return titles + links without article text, which
makes the health check flag them as "body extract abnormal". These helpers
fetch each article over plain HTTP (reusing the crawler's aiohttp session —
a browser per article would blow the health-check time budget) and try to
extract the main text with broad heuristics.
"""
import asyncio
import logging
import re
import time
from typing import List

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_NOISE_ATTRS = [
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", "button",
]


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_main_text(html: str) -> str:
    """Best-effort extraction of the main article text from raw HTML."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NOISE_ATTRS):
        tag.decompose()
    for selector in (
        ".ad", ".ads", ".advert", ".advertisement", ".banner", ".recommend",
        ".related", ".comment", ".share", ".video", ".promotion", ".tips",
        ".gdt", ".iframe_container",
    ):
        for node in soup.select(selector):
            node.decompose()

    candidates = (
        "article",
        "[itemprop='articleBody']",
        ".article-content", ".article_content", ".articleContent", ".article",
        ".content", ".post-content", ".entry-content", ".article-detail",
        ".news-content", ".newsContent", ".main-content", ".detail-content",
        ".rich_media_content", ".article-body", ".article_content_xq",
        ".detail_con", "#content", ".text", ".txt", ".con",
    )
    for selector in candidates:
        node = soup.select_one(selector)
        if not node:
            continue
        text = _collapse(" ".join(p.get_text(" ", strip=True) for p in node.find_all("p")))
        if len(text) < 40:
            text = _collapse(node.get_text(" ", strip=True))
        if len(text) >= 40:
            return text

    # Fallback: join all reasonably-sized paragraphs.
    parts = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = _collapse(" ".join(part for part in parts if len(part) > 20))
    return text


async def _fetch_article_text(crawler, url: str, timeout: float) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        html = await asyncio.wait_for(crawler.fetch_url(url), timeout=timeout)
    except Exception:
        return ""
    return extract_main_text(html)


async def enrich_items(
    crawler,
    items: List,
    *,
    limit: int = 10,
    concurrency: int = 4,
    per_item_timeout: float = 8.0,
    budget: float = 24.0,
) -> None:
    """Fetch article bodies for items that lack text, within a time budget.

    Only items whose `content`/`summary` is already >= 40 chars are skipped.
    Never raises: it is a best-effort enrichment pass.
    """
    targets = [
        item for item in items
        if item and not ((item.content and len(item.content) >= 40) or (item.summary and len(item.summary) >= 40))
    ][:limit]
    if not targets:
        return

    sem = asyncio.Semaphore(concurrency)
    started = time.monotonic()
    enriched = 0

    async def work(item):
        nonlocal enriched
        async with sem:
            if time.monotonic() - started > budget:
                return
            text = await _fetch_article_text(crawler, item.url, per_item_timeout)
            if len(text) >= 40:
                item.content = text
                if not item.summary or len(item.summary) < 40:
                    item.summary = text[:200]
                enriched += 1

    await asyncio.gather(*[work(item) for item in targets], return_exceptions=True)
    logger.info("[%s] enriched %d/%d items", getattr(crawler, "name", "?"), enriched, len(targets))