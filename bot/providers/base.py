from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class MediaTitle:
    provider: str
    external_id: str
    title: str
    format: str  # ANIME or MANGA
    url: str
    cover_url: str = ""
    description: str = ""
    status: str = "UNKNOWN"
    episodes: int | None = None
    chapters: int | None = None
    next_airing_at: int | None = None  # UTC Unix timestamp
    next_episode: int | None = None
    start_date: str = ""
    end_date: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReleaseItem:
    release_key: str
    title: str
    format: str
    update_type: str
    number: int | None
    release_at: int | None  # UTC Unix timestamp
    status: str  # scheduled, estimated, officially_confirmed, verified, unverified
    source: str
    url: str
    summary: str = ""
    official: bool = False


@dataclass(slots=True)
class NewsItem:
    item_id: str
    title: str
    summary: str
    url: str
    source: str
    published_at: int | None
    official: bool = False


class Provider(Protocol):
    name: str

    async def search(self, query: str, media_format: str = "ANIME", limit: int = 8) -> list[MediaTitle]: ...

    async def get(self, external_id: str, media_format: str = "ANIME") -> MediaTitle | None: ...
