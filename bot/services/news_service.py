from __future__ import annotations

import logging
import time
from typing import Any

from ..database.repositories import Repository
from ..providers.official_sources import OfficialSourcesProvider

log = logging.getLogger(__name__)


class NewsService:
    def __init__(self, repo: Repository, provider: OfficialSourcesProvider):
        self.repo = repo
        self.provider = provider

    async def poll(self) -> int:
        if not self.provider.feeds:
            return 0
        # Track feed initialization independently so adding a feed does not replay its whole archive.
        prior_health = {}
        for name, _url, _official in self.provider.feeds:
            prior_health[name] = await self.repo.db.fetchone("SELECT last_success_at FROM source_health WHERE source=?", (f"RSS:{name}",))
        items = await self.provider.fetch()
        failed_names = {message.split(":", 1)[0] for message in self.provider.last_errors}
        for name, _url, _official in self.provider.feeds:
            if name not in failed_names:
                await self.repo.source_succeeded(f"RSS:{name}")
        if self.provider.last_errors:
            await self.repo.source_failed("RSS", "; ".join(self.provider.last_errors))
        else:
            await self.repo.source_succeeded("RSS")
        tracked = await self.repo.all_tracked_titles()
        made = 0
        now = int(time.time())
        for item in items:
            is_new = await self.repo.mark_feed_item_seen(item.item_id, item.source)
            baseline = not prior_health.get(item.source) or not prior_health[item.source].get("last_success_at")
            # First successful feed pass seeds current items. Later passes only process new entry IDs.
            # Mark old entries as seen but don't replay back-catalogue news after a long outage.
            if baseline or not is_new or item.published_at is None or item.published_at < now - 48 * 3600:
                continue
            haystack = f"{item.title} {item.summary}".casefold()
            for track in tracked:
                term = str(track.get("title") or "").casefold()
                if not term or not ((len(term) >= 4 and term in haystack) or haystack.startswith(term)):
                    continue
                body = haystack
                if any(word in body for word in ("delayed", "delay announcement", "postponed", "rescheduled")):
                    update_type = "delay"
                elif any(word in body for word in ("hiatus", "on hiatus", "temporary break")):
                    update_type = "hiatus"
                elif any(word in body for word in ("cancelled", "canceled", "cancelation", "cancellation")):
                    update_type = "cancelled"
                elif any(word in body for word in ("returns", "return date", "resumes", "back from hiatus")):
                    update_type = "return"
                elif any(word in body for word in ("new season", "season 2", "season 3", "season two", "sequel announced")):
                    update_type = "new_season" if item.official else "news_report"
                else:
                    update_type = "official_announcement" if item.official else "news_report"
                if await self.repo.create_news_event(track, item, update_type=update_type):
                    made += 1
        return made

    async def search(self, title: str, limit: int = 10) -> list[dict[str, Any]]:
        items = await self.provider.fetch()
        term = title.casefold().strip()
        matches = []
        for item in items:
            content = f"{item.title} {item.summary}".casefold()
            if term and term in content:
                matches.append({"title": item.title, "summary": item.summary, "url": item.url, "source": item.source,
                                "published_at": item.published_at, "official": item.official, "item_id": item.item_id})
        matches.sort(key=lambda x: x.get("published_at") or 0, reverse=True)
        return matches[:limit]

    async def upcoming_announcements(self, tracks: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
        # RSS doesn't supply trustworthy machine-readable episode or chapter dates universally.
        # Return relevant announcements, plus the catalogue's explicitly scheduled anime airing data.
        latest: list[dict[str, Any]] = []
        for item in await self.provider.fetch():
            body = f"{item.title} {item.summary}".casefold()
            for track in tracks:
                title = str(track.get("title") or "").casefold()
                if title and len(title) >= 4 and title in body:
                    latest.append({"title": item.title, "summary": item.summary, "url": item.url, "source": item.source,
                                   "published_at": item.published_at, "official": item.official, "tracked_title": track.get("title")})
                    break
        latest.sort(key=lambda x: x.get("published_at") or 0, reverse=True)
        return latest[:limit]
