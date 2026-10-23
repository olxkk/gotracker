from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from .base import MediaTitle

GRAPHQL_URL = "https://graphql.anilist.co"
MEDIA_FIELDS = """
 id type format status episodes chapters genres siteUrl description(asHtml:false)
 title { romaji english native }
 coverImage { large }
 startDate { year month day } endDate { year month day }
 nextAiringEpisode { airingAt timeUntilAiring episode }
"""

# Random discovery only needs compact card fields. Including descriptions here can make
# a single 25-result response exceed the configured response-size limit.
RANDOM_MEDIA_FIELDS = """
 id type format status episodes chapters genres siteUrl
 title { romaji english native }
 coverImage { large }
 startDate { year month day } endDate { year month day }
 nextAiringEpisode { airingAt timeUntilAiring episode }
"""


class AniListProvider:
    name = "AniList"

    def __init__(self, session: aiohttp.ClientSession | None = None, timeout: int = 15, max_bytes: int = 2_000_000):
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_bytes = max_bytes
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("AniList provider has no HTTP session")
        async with self._lock:
            # Gentle pacing protects against bursts as well as the published rate limit.
            delay = 2.5 - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()
        for attempt in range(3):
            try:
                async with self.session.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    timeout=self.timeout,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                ) as response:
                    raw = await response.content.read(self.max_bytes + 1)
                    if len(raw) > self.max_bytes:
                        raise ValueError("AniList response exceeded configured size limit")
                    if response.status == 429 and attempt < 2:
                        try:
                            retry_text = response.headers.get("Retry-After", "5")
                            wait = min(60, max(1, int(retry_text)))
                        except ValueError:
                            wait = 5
                        await asyncio.sleep(wait)
                        continue
                    if response.status >= 500 and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if response.status >= 400:
                        raise RuntimeError(f"AniList returned HTTP {response.status}")
                    try:
                        payload = await _json_loads(raw)
                    except Exception as exc:
                        raise ValueError("AniList returned invalid JSON") from exc
                    if payload.get("errors"):
                        message = str(payload["errors"][0].get("message", "GraphQL error"))[:200]
                        raise RuntimeError(f"AniList API error: {message}")
                    return payload.get("data") or {}
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt >= 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("AniList request failed after retries")

    async def search(self, query: str, media_format: str = "ANIME", limit: int = 8) -> list[MediaTitle]:
        if not query.strip():
            return []
        graphql = f"query ($search: String, $type: MediaType, $perPage: Int) {{ Page(perPage: $perPage) {{ media(search: $search, type: $type, sort: SEARCH_MATCH) {{{MEDIA_FIELDS}}} }} }}"
        data = await self._graphql(graphql, {"search": query.strip()[:100], "type": _media_type(media_format), "perPage": min(max(limit, 1), 10)})
        return [_from_anilist(row) for row in data.get("Page", {}).get("media", []) if isinstance(row, dict)]


    async def random_anime(
        self,
        category: str,
        minimum_score: int = 75,
        genre: str | None = None,
        max_episodes: int | None = None,
        year: int | None = None,
    ) -> tuple[MediaTitle, int] | None:
        """Pick a real AniList anime, applying optional discovery filters."""
        import random

        category = str(category).upper()
        if category not in {"RELEASING", "FINISHED", "HIGH_RATED"}:
            raise ValueError("Unsupported random anime category")
        minimum_score = min(100, max(1, int(minimum_score)))
        if max_episodes is not None:
            max_episodes = min(100, max(1, int(max_episodes)))
        if year is not None:
            year = min(2100, max(1970, int(year)))
        genre = str(genre).strip() if genre else None
        if genre and genre not in {
            "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror", "Mahou Shoujo",
            "Mecha", "Music", "Mystery", "Psychological", "Romance", "Sci-Fi", "Slice of Life",
            "Sports", "Supernatural", "Thriller"
        }:
            raise ValueError("Unsupported anime genre")

        # Random pages prevent the command from always returning the most popular titles.
        # The API still determines eligibility; every returned result is checked locally too.
        for _ in range(8):
            page = random.randint(1, 40)
            filters = ["type: ANIME"]
            declarations = ["$page: Int", "$perPage: Int"]
            variables: dict[str, Any] = {"page": page, "perPage": 25}
            if category != "HIGH_RATED":
                declarations.append("$status: MediaStatus")
                variables["status"] = category
                filters.append("status: $status")
            else:
                declarations.append("$score: Int")
                variables["score"] = max(0, minimum_score - 1)
                filters.append("averageScore_greater: $score")
            if genre:
                declarations.append("$genres: [String]")
                variables["genres"] = [genre]
                filters.append("genre_in: $genres")
            if max_episodes is not None:
                declarations.append("$maxEpisodes: Int")
                variables["maxEpisodes"] = max_episodes + 1
                filters.append("episodes_lesser: $maxEpisodes")
            if year is not None:
                declarations.append("$year: Int")
                variables["year"] = year
                filters.append("seasonYear: $year")
            sort = "SCORE_DESC" if category == "HIGH_RATED" else "POPULARITY_DESC"
            graphql = (
                f"query ({', '.join(declarations)}) {{ Page(page: $page, perPage: $perPage) "
                f"{{ media({', '.join(filters)}, sort: {sort}) {{{RANDOM_MEDIA_FIELDS} averageScore}} }} }}"
            )
            data = await self._graphql(graphql, variables)
            rows = data.get("Page", {}).get("media", [])
            eligible = []
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                status = str(row.get("status") or "UNKNOWN").upper()
                score = row.get("averageScore")
                episodes = row.get("episodes")
                row_genres = row.get("genres") or []
                start_date = row.get("startDate") or {}
                if category == "RELEASING" and status != "RELEASING":
                    continue
                if category == "FINISHED" and status != "FINISHED":
                    continue
                if category == "HIGH_RATED" and (not isinstance(score, int) or score < minimum_score):
                    continue
                if genre and genre not in row_genres:
                    continue
                if max_episodes is not None and (not isinstance(episodes, int) or episodes > max_episodes):
                    continue
                if year is not None and start_date.get("year") != year:
                    continue
                eligible.append((row, int(score) if isinstance(score, int) else 0))
            if eligible:
                row, score = random.choice(eligible)
                return _from_anilist(row), score
        return None

    async def get(self, external_id: str, media_format: str = "ANIME") -> MediaTitle | None:
        try:
            media_id = int(external_id)
        except (TypeError, ValueError):
            return None
        graphql = f"query ($id: Int, $type: MediaType) {{ Media(id: $id, type: $type) {{{MEDIA_FIELDS}}} }}"
        data = await self._graphql(graphql, {"id": media_id, "type": _media_type(media_format)})
        item = data.get("Media")
        return _from_anilist(item) if isinstance(item, dict) else None


def _media_type(media_format: str) -> str:
    return "MANGA" if str(media_format).upper() == "MANGA" else "ANIME"


def _date_parts(value: Any) -> str:
    if not isinstance(value, dict) or not value.get("year"):
        return ""
    return f"{int(value['year']):04d}-{int(value.get('month') or 1):02d}-{int(value.get('day') or 1):02d}"


def _from_anilist(row: dict[str, Any]) -> MediaTitle:
    titles = row.get("title") or {}
    title = titles.get("english") or titles.get("romaji") or titles.get("native") or f"AniList #{row.get('id')}"
    next_airing = row.get("nextAiringEpisode") or {}
    status = str(row.get("status") or "UNKNOWN").upper()
    return MediaTitle(
        provider="anilist", external_id=str(row.get("id")), title=str(title)[:250],
        format=_media_type(row.get("type", "ANIME")), url=str(row.get("siteUrl") or f"https://anilist.co/{str(row.get('type','ANIME')).lower()}/{row.get('id')}"),
        cover_url=str((row.get("coverImage") or {}).get("large") or "")[:1000],
        description=str(row.get("description") or "")[:1500], status=status,
        episodes=_optional_int(row.get("episodes")), chapters=_optional_int(row.get("chapters")),
        next_airing_at=_optional_int(next_airing.get("airingAt")), next_episode=_optional_int(next_airing.get("episode")),
        start_date=_date_parts(row.get("startDate")), end_date=_date_parts(row.get("endDate")), source_url=str(row.get("siteUrl") or ""),
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _json_loads(raw: bytes) -> dict[str, Any]:
    import json
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value
