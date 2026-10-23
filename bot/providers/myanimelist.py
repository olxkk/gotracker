from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .base import MediaTitle


class MyAnimeListProvider:
    name = "MyAnimeList"
    BASE_URL = "https://api.myanimelist.net/v2"
    ANIME_FIELDS = "id,title,main_picture,start_date,end_date,synopsis,status,num_episodes,media_type"
    MANGA_FIELDS = "id,title,main_picture,start_date,end_date,synopsis,status,num_chapters,media_type"

    def __init__(self, client_id: str = "", session: aiohttp.ClientSession | None = None, timeout: int = 15, max_bytes: int = 2_000_000):
        self.client_id = client_id.strip()
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_bytes = max_bytes

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.client_id:
            raise RuntimeError("MyAnimeList is disabled: set MAL_CLIENT_ID to enable it")
        if self.session is None:
            raise RuntimeError("MyAnimeList provider has no HTTP session")
        for attempt in range(3):
            try:
                async with self.session.get(f"{self.BASE_URL}/{path}", params=params, timeout=self.timeout,
                                           headers={"X-MAL-CLIENT-ID": self.client_id, "Accept": "application/json"}) as response:
                    raw = await response.content.read(self.max_bytes + 1)
                    if len(raw) > self.max_bytes:
                        raise ValueError("MyAnimeList response exceeded configured size limit")
                    if response.status == 429 and attempt < 2:
                        try:
                            retry_text = response.headers.get("Retry-After", str(2 ** attempt))
                            wait = min(30, max(1, int(retry_text)))
                        except ValueError:
                            wait = 2 ** attempt
                        await asyncio.sleep(wait)
                        continue
                    if response.status >= 500 and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if response.status >= 400:
                        raise RuntimeError(f"MyAnimeList returned HTTP {response.status}")
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ValueError("MyAnimeList returned unexpected JSON")
                    return value
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt >= 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("MyAnimeList request failed after retries")

    async def search(self, query: str, media_format: str = "ANIME", limit: int = 8) -> list[MediaTitle]:
        if not self.client_id or not query.strip():
            return []
        resource = "manga" if media_format.upper() == "MANGA" else "anime"
        fields = self.MANGA_FIELDS if resource == "manga" else self.ANIME_FIELDS
        payload = await self._get_json(resource, {"q": query.strip()[:100], "limit": str(min(max(limit, 1), 10)), "fields": fields})
        result = []
        for row in payload.get("data", []):
            node = row.get("node", {}) if isinstance(row, dict) else {}
            if node:
                result.append(_from_mal(node, media_format))
        return result

    async def get(self, external_id: str, media_format: str = "ANIME") -> MediaTitle | None:
        if not self.client_id or not str(external_id).isdigit():
            return None
        resource = "manga" if media_format.upper() == "MANGA" else "anime"
        fields = self.MANGA_FIELDS if resource == "manga" else self.ANIME_FIELDS
        payload = await self._get_json(f"{resource}/{external_id}", {"fields": fields})
        return _from_mal(payload, media_format) if payload.get("id") else None


def _from_mal(row: dict[str, Any], media_format: str) -> MediaTitle:
    fmt = "MANGA" if media_format.upper() == "MANGA" else "ANIME"
    ident = str(row.get("id", ""))
    picture = row.get("main_picture") or {}
    return MediaTitle(
        provider="myanimelist", external_id=ident, title=str(row.get("title") or f"MyAnimeList #{ident}")[:250], format=fmt,
        url=f"https://myanimelist.net/{'manga' if fmt == 'MANGA' else 'anime'}/{ident}",
        cover_url=str(picture.get("large") or picture.get("medium") or "")[:1000],
        description=str(row.get("synopsis") or "")[:1500], status=str(row.get("status") or "UNKNOWN").upper(),
        episodes=_int_or_none(row.get("num_episodes")), chapters=_int_or_none(row.get("num_chapters")),
        start_date=str(row.get("start_date") or ""), end_date=str(row.get("end_date") or ""),
        source_url=f"https://myanimelist.net/{'manga' if fmt == 'MANGA' else 'anime'}/{ident}",
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
