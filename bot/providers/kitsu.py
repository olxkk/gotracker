from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .base import MediaTitle

BASE_URL = "https://kitsu.io/api/edge"


class KitsuProvider:
    name = "Kitsu"

    def __init__(self, session: aiohttp.ClientSession | None = None, timeout: int = 15, max_bytes: int = 2_000_000):
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_bytes = max_bytes

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("Kitsu provider has no HTTP session")
        for attempt in range(3):
            try:
                async with self.session.get(f"{BASE_URL}/{path}", params=params, timeout=self.timeout,
                                           headers={"Accept": "application/vnd.api+json", "User-Agent": "AnimeMangaTracker/1.0"}) as response:
                    raw = await response.content.read(self.max_bytes + 1)
                    if len(raw) > self.max_bytes:
                        raise ValueError("Kitsu response exceeded configured size limit")
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
                        raise RuntimeError(f"Kitsu returned HTTP {response.status}")
                    payload = json.loads(raw.decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("Kitsu returned unexpected JSON")
                    return payload
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt >= 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("Kitsu request failed after retries")

    async def search(self, query: str, media_format: str = "ANIME", limit: int = 8) -> list[MediaTitle]:
        if not query.strip():
            return []
        resource = "manga" if media_format.upper() == "MANGA" else "anime"
        payload = await self._get_json(resource, {"filter[text]": query.strip()[:100], "page[limit]": str(min(max(limit, 1), 10))})
        return [_from_kitsu(item, media_format) for item in payload.get("data", []) if isinstance(item, dict)]

    async def get(self, external_id: str, media_format: str = "ANIME") -> MediaTitle | None:
        if not str(external_id).isdigit():
            return None
        resource = "manga" if media_format.upper() == "MANGA" else "anime"
        payload = await self._get_json(f"{resource}/{external_id}", {})
        item = payload.get("data")
        return _from_kitsu(item, media_format) if isinstance(item, dict) else None


def _from_kitsu(item: dict[str, Any], media_format: str) -> MediaTitle:
    attrs = item.get("attributes") or {}
    title = attrs.get("canonicalTitle") or attrs.get("titles", {}).get("en") or attrs.get("titles", {}).get("en_jp") or "Untitled"
    res_id = str(item.get("id", ""))
    media_format = "MANGA" if media_format.upper() == "MANGA" else "ANIME"
    cover = attrs.get("posterImage") or {}
    status_map = {"current": "RELEASING", "finished": "FINISHED", "upcoming": "NOT_YET_RELEASED", "unreleased": "NOT_YET_RELEASED"}
    return MediaTitle(
        provider="kitsu", external_id=res_id, title=str(title)[:250], format=media_format,
        url=f"https://kitsu.io/{'manga' if media_format == 'MANGA' else 'anime'}/{res_id}",
        cover_url=str(cover.get("large") or cover.get("original") or "")[:1000],
        description=str(attrs.get("synopsis") or "")[:1500], status=status_map.get(str(attrs.get("status") or "").lower(), str(attrs.get("status") or "UNKNOWN").upper()),
        episodes=_int_or_none(attrs.get("episodeCount")), chapters=_int_or_none(attrs.get("chapterCount")),
        start_date=str(attrs.get("startDate") or ""), end_date=str(attrs.get("endDate") or ""), source_url=f"https://kitsu.io/{'manga' if media_format == 'MANGA' else 'anime'}/{res_id}",
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
