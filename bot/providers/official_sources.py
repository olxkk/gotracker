from __future__ import annotations

import asyncio
import calendar
import hashlib
import re
import time
from email.utils import parsedate_to_datetime
from typing import Iterable

import aiohttp
import feedparser

from .base import NewsItem


class OfficialSourcesProvider:
    """Reads only operator-configured RSS/Atom feeds; it does not scrape websites."""
    name = "RSS/official sources"

    def __init__(self, feeds: Iterable[tuple[str, str, bool]] = (), session: aiohttp.ClientSession | None = None,
                 timeout: int = 15, max_bytes: int = 1_000_000, user_agent: str = "AnimeMangaTracker/1.0"):
        self.feeds = list(feeds)
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.last_errors: list[str] = []

    async def fetch(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        self.last_errors = []
        if not self.feeds or self.session is None:
            return items
        for source_name, url, official in self.feeds:
            raw = None
            for attempt in range(3):
                try:
                    async with self.session.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}) as response:
                        if response.status == 429 or response.status >= 500:
                            if attempt < 2:
                                try:
                                    retry_after = int(response.headers.get("Retry-After", str(2 ** attempt)))
                                except (TypeError, ValueError):
                                    retry_after = 2 ** attempt
                                await asyncio.sleep(min(30, max(1, retry_after)))
                                continue
                            self.last_errors.append(f"{source_name}: HTTP {response.status}")
                            break
                        if response.status >= 400:
                            self.last_errors.append(f"{source_name}: HTTP {response.status}")
                            break
                        candidate = await response.content.read(self.max_bytes + 1)
                        if len(candidate) > self.max_bytes:
                            self.last_errors.append(f"{source_name}: response too large")
                            break
                        raw = candidate
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    self.last_errors.append(f"{source_name}: {type(exc).__name__}")
            if raw is None:
                continue
            try:
                parsed = feedparser.parse(raw)
                if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
                    self.last_errors.append(f"{source_name}: invalid feed")
                    continue
                for entry in parsed.entries[:50]:
                    title = _safe_text(entry.get("title", ""), 250)
                    link = str(entry.get("link", ""))[:1000]
                    if not title or not link.startswith(("https://", "http://")):
                        continue
                    summary = _safe_text(entry.get("summary", entry.get("description", "")), 500)
                    stamp = None
                    raw_date = entry.get("published") or entry.get("updated")
                    if raw_date:
                        try:
                            stamp = int(parsedate_to_datetime(raw_date).timestamp())
                        except (TypeError, ValueError, OverflowError):
                            try:
                                stamp = int(calendar.timegm(entry.get("published_parsed"))) if entry.get("published_parsed") else None
                            except (TypeError, ValueError, OverflowError):
                                stamp = None
                    item_id = str(entry.get("id") or link or title)
                    fingerprint = hashlib.sha256(f"{source_name}|{item_id}".encode()).hexdigest()
                    items.append(NewsItem(fingerprint, title, summary, link, source_name[:80], stamp, official))
            except (ValueError, TypeError, AttributeError) as exc:
                self.last_errors.append(f"{source_name}: {type(exc).__name__}")
                continue
        return items


def _safe_text(value: object, limit: int) -> str:
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]

