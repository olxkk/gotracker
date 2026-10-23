from __future__ import annotations

import hashlib
import time
from typing import Any

from ..database.repositories import Repository
from ..providers.base import MediaTitle, Provider, ReleaseItem


class ProviderRegistry:
    def __init__(self, anilist: Provider, kitsu: Provider, mal: Provider, mangadex: Provider | None = None):
        self.providers = {"anilist": anilist, "kitsu": kitsu, "myanimelist": mal}
        if mangadex is not None:
            self.providers["mangadex"] = mangadex

    async def search(self, query: str, media_format: str = "ANIME", limit: int = 8, source: str | None = None) -> list[MediaTitle]:
        gathered: list[MediaTitle] = []
        # MangaDex is a manga-only catalogue; never query it for anime.
        if source:
            key = source.casefold().strip()
            provider = self.providers.get(key)
            if provider is None or (key == "mangadex" and str(media_format).upper() != "MANGA"):
                return []
            return await provider.search(query, media_format, limit=max(1, min(limit, 10)))
        # AniList is intentionally first: it is the primary schedule source.
        keys = ("anilist", "kitsu", "myanimelist") if str(media_format).upper() != "MANGA" else ("anilist", "kitsu", "myanimelist")
        for key in keys:
            try:
                results = await self.providers[key].search(query, media_format, limit=max(1, min(limit, 8)))
            except Exception:
                continue
            for result in results:
                if not any(x.provider == result.provider and x.external_id == result.external_id for x in gathered):
                    gathered.append(result)
                if len(gathered) >= limit:
                    return gathered
        return gathered

    def get_provider(self, provider: str) -> Provider | None:
        return self.providers.get(provider)

    async def get(self, provider: str, external_id: str, media_format: str = "ANIME") -> MediaTitle | None:
        implementation = self.get_provider(provider)
        if implementation is None:
            return None
        return await implementation.get(external_id, media_format)


class ReleaseService:
    def __init__(self, repo: Repository, providers: ProviderRegistry):
        self.repo = repo
        self.providers = providers

    async def refresh(self, provider: str, external_id: str, media_format: str = "ANIME") -> tuple[MediaTitle | None, list[ReleaseItem]]:
        now = int(time.time())
        old = await self.repo.get_media(provider, external_id)
        fresh = await self.providers.get(provider, external_id, media_format)
        if fresh is None:
            return None, []
        events: list[ReleaseItem] = []
        previous_at = old.get("next_airing_at") if old else None
        previous_ep = old.get("next_episode") if old else None
        if old and fresh.format == "ANIME" and previous_at and fresh.next_airing_at != previous_at:
            previous_at = int(previous_at)
            previous_ep = int(previous_ep) if previous_ep is not None else None
            fresh_ep = fresh.next_episode
            if previous_at <= now:
                # A schedule advancing proves only that the planned time passed, not that a platform made it available.
                key = _key(provider, external_id, "episode_window_passed", previous_ep, previous_at)
                events.append(ReleaseItem(key, fresh.title, fresh.format, "episode_window_passed", previous_ep, previous_at,
                                          "unverified", "AniList airing schedule", fresh.url,
                                          "The scheduled airing window has passed. Availability is not verified by AniList.", False))
            elif fresh.next_airing_at and previous_ep == fresh_ep:
                changed_at = int(fresh.next_airing_at)
                delay = changed_at > previous_at + 60
                event_type = "delay" if delay else "schedule_change"
                key = _key(provider, external_id, event_type, fresh_ep, changed_at)
                summary = "The next airing time moved later; this is a schedule-derived delay and is not an official announcement." if delay else "The airing schedule changed; verify the date at the linked source."
                events.append(ReleaseItem(key, fresh.title, fresh.format, event_type, fresh_ep, changed_at,
                                          "estimated", "AniList airing schedule", fresh.url, summary, False))
            elif fresh.next_airing_at and fresh_ep != previous_ep:
                changed_at = int(fresh.next_airing_at)
                key = _key(provider, external_id, "schedule_change", fresh_ep, changed_at)
                events.append(ReleaseItem(key, fresh.title, fresh.format, "schedule_change", fresh_ep, changed_at,
                                          "scheduled", "AniList airing schedule", fresh.url,
                                          "The provider advanced to a different upcoming episode schedule; availability of the previous episode is not verified.", False))
        # A fresh entry can show upcoming schedule data, but the initial tracked snapshot is baseline-only.
        if old and fresh.format == "ANIME" and fresh.next_airing_at and int(fresh.next_airing_at) > now:
            schedule_changed = old.get("next_airing_at") != fresh.next_airing_at
            number_changed = old.get("next_episode") != fresh.next_episode
            if schedule_changed and number_changed and int(fresh.next_airing_at) <= now + 14 * 86400:
                key = _key(provider, external_id, "upcoming_episode", fresh.next_episode, fresh.next_airing_at)
                events.append(ReleaseItem(key, fresh.title, fresh.format, "upcoming_episode", fresh.next_episode, fresh.next_airing_at,
                                          "scheduled", "AniList airing schedule", fresh.url,
                                          "Scheduled airing time from AniList; availability is not confirmed.", False))
        if old and old.get("status") and str(old.get("status")).upper() != fresh.status.upper():
            old_status = str(old.get("status")).upper()
            new_status = fresh.status.upper()
            event_type = None
            if new_status == "CANCELLED":
                event_type = "cancelled"
            elif new_status == "HIATUS":
                event_type = "hiatus"
            elif old_status == "HIATUS" and new_status in {"RELEASING", "NOT_YET_RELEASED"}:
                event_type = "return"
            if event_type:
                key = _key(provider, external_id, event_type, None, now)
                events.append(ReleaseItem(key, fresh.title, fresh.format, event_type, None, now, "unverified",
                                          "AniList metadata status", fresh.url,
                                          f"Catalog status changed from {old_status} to {new_status}. This is a metadata status change, not a separately verified official announcement.", False))
        # MangaDex's catalogue doesn't supply chapter totals. Poll its chapter feed and
        # emit a deduplicated event when the highest whole English chapter advances.
        if fresh.format == "MANGA" and provider == "mangadex":
            implementation = self.providers.get_provider("mangadex")
            if implementation and hasattr(implementation, "latest_english_chapter"):
                try:
                    chapter_number, chapter_id, chapter_url = await implementation.latest_english_chapter(external_id)
                except Exception:
                    chapter_number = chapter_id = chapter_url = None
                if chapter_number is not None:
                    previous_chapter = (old or {}).get("chapters")
                    fresh.chapters = int(chapter_number)
                    if old and previous_chapter is not None and int(previous_chapter) < int(chapter_number):
                        chapter_link = chapter_url or fresh.url
                        key = _key(provider, external_id, "new_chapter", int(chapter_number), now)
                        events.append(ReleaseItem(key, fresh.title, "MANGA", "new_chapter", int(chapter_number), now,
                                                  "verified", "MangaDex English chapter feed", chapter_link,
                                                  f"MangaDex lists English chapter {int(chapter_number)}.", False))
        await self.repo.save_media(fresh, checked_at=now)
        await self.repo.db.execute("UPDATE tracked_titles SET last_checked_at=? WHERE provider=? AND external_id=?", (now, provider, external_id))
        for event in events:
            await self.repo.add_release(event, provider, external_id)
        return fresh, events


def _key(provider: str, external_id: str, event_type: str, number: int | None, stamp: int | None) -> str:
    raw = f"{provider}|{external_id}|{event_type}|{number if number is not None else 'unknown'}|{stamp if stamp is not None else 'unknown'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def latest_release_events(repo: Repository, track: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    return await repo.get_events(track["provider"], track["external_id"], limit)
