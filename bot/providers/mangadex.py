from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .base import MediaTitle

API = "https://api.mangadex.org"


class MangaDexProvider:
    """MangaDex manga search and latest English whole-chapter snapshot provider."""
    name = "MangaDex"

    def __init__(self, session: aiohttp.ClientSession | None = None, timeout: int = 15, max_bytes: int = 2_000_000):
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_bytes = max_bytes
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("MangaDex provider has no HTTP session")
        async with self._lock:
            delay = 0.35 - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()
        async with self.session.get(API + path, params=params, timeout=self.timeout, headers={"Accept": "application/json"}) as response:
            raw = await response.content.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                raise ValueError("MangaDex response exceeded configured size limit")
            if response.status == 429:
                raise RuntimeError("MangaDex rate limit reached; try again later")
            if response.status >= 400:
                raise RuntimeError(f"MangaDex returned HTTP {response.status}")
            import json
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MangaDex returned an invalid response")
            return payload

    async def search(self, query: str, media_format: str = "MANGA", limit: int = 8) -> list[MediaTitle]:
        if str(media_format).upper() != "MANGA" or not query.strip():
            return []
        query = query.strip()
        if "mangadex.org/title/" in query:
            exact = await self.get(query, "MANGA")
            return [exact] if exact else []
        payload = await self._get_json("/manga", {"title": query[:100], "limit": min(max(int(limit), 1), 10), "order[relevance]": "desc", "includes[]": ["cover_art"]})
        return [self._from_row(row) for row in payload.get("data", []) if isinstance(row, dict)]

    async def get(self, external_id: str, media_format: str = "MANGA") -> MediaTitle | None:
        if str(media_format).upper() != "MANGA":
            return None
        manga_id = external_id.strip()
        # Accept a canonical MangaDex UUID or a MangaDex URL, but never arbitrary URLs.
        if "mangadex.org/title/" in manga_id:
            manga_id = manga_id.split("mangadex.org/title/", 1)[1].split("/", 1)[0].split("?", 1)[0]
        if len(manga_id) != 36 or manga_id.count("-") != 4:
            return None
        payload = await self._get_json(f"/manga/{quote(manga_id, safe='-')}", {"includes[]": ["cover_art"]})
        row = payload.get("data")
        return self._from_row(row) if isinstance(row, dict) else None

    async def latest_english_chapter(self, manga_id: str) -> tuple[int | None, str | None, str | None]:
        """Return newest English whole chapter number, chapter UUID and URL."""
        payload = await self._get_json("/chapter", {
            "manga[]": manga_id, "translatedLanguage[]": ["en"], "includeExternalUrl": "0",
            "order[chapter]": "desc", "limit": "100", "contentRating[]": ["safe", "suggestive", "erotica"],
        })
        rows = payload.get("data", [])
        # API chapter ordering is lexical; numeric parsing and max() avoid 9 being chosen over 10.
        candidates: list[tuple[int, str, str]] = []
        for row in rows:
            attrs = row.get("attributes") or {}
            raw = attrs.get("chapter")
            if raw is None:
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if number < 0 or not number.is_integer():
                continue
            chapter_id = str(row.get("id") or "")
            if chapter_id:
                candidates.append((int(number), chapter_id, f"https://mangadex.org/chapter/{chapter_id}"))
        if not candidates:
            return None, None, None
        number, chapter_id, url = max(candidates, key=lambda item: (item[0], item[1]))
        return number, chapter_id, url

    def _from_row(self, row: dict[str, Any]) -> MediaTitle:
        attrs = row.get("attributes") or {}
        titles = attrs.get("title") or {}
        alt = attrs.get("altTitles") or []
        title = titles.get("en") or next(iter(titles.values()), None)
        if not title:
            for entry in alt:
                if isinstance(entry, dict) and entry:
                    title = next(iter(entry.values()), None)
                    if title:
                        break
        manga_id = str(row.get("id") or "")
        cover_file = ""
        for relation in row.get("relationships") or []:
            if relation.get("type") == "cover_art":
                cover_file = str((relation.get("attributes") or {}).get("fileName") or "")
                if not cover_file:
                    # Some API responses include only the relation ID; don't make another call per result.
                    cover_file = ""
                break
        cover = f"https://uploads.mangadex.org/covers/{manga_id}/{quote(cover_file)}.256.jpg" if cover_file else ""
        status = str(attrs.get("status") or "UNKNOWN").upper()
        return MediaTitle(provider="mangadex", external_id=manga_id, title=str(title or f"MangaDex title {manga_id[:8]}")[:250],
                          format="MANGA", url=f"https://mangadex.org/title/{manga_id}", cover_url=cover,
                          description=str(attrs.get("description", {}).get("en", "") if isinstance(attrs.get("description"), dict) else "")[:1500],
                          status=status, chapters=None, source_url=f"https://mangadex.org/title/{manga_id}")
