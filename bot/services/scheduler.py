from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict

from ..database.repositories import Repository
from ..providers.official_sources import OfficialSourcesProvider
from .news_service import NewsService
from .notification_service import NotificationService
from .release_service import ProviderRegistry, ReleaseService

log = logging.getLogger(__name__)


class Scheduler:
    """Single persistent loop. One lock serializes scheduled and manual refreshes."""
    def __init__(self, repo: Repository, providers: ProviderRegistry, release_service: ReleaseService,
                 news_service: NewsService, notifications: NotificationService, interval_seconds: int = 60):
        self.repo = repo
        self.providers = providers
        self.release_service = release_service
        self.news_service = news_service
        self.notifications = notifications
        self.interval_seconds = max(60, int(interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self.last_cycle: dict[str, int] | None = None
        self.last_cycle_at: int | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run_forever(), name="anime-manga-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run_forever(self) -> None:
        # Run once at startup, then sleep. The task is created in setup_hook, not on reconnect.
        while not self._stop.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Unexpected error in monitoring cycle")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def run_once(self) -> dict[str, int]:
        async with self._run_lock:
            unique = OrderedDict()
            for track in await self.repo.all_tracked_titles():
                unique[(track["provider"], str(track["external_id"]), track["format"])] = track
            checked = errors = 0
            for (provider, external_id, media_format), _ in unique.items():
                source = provider
                await self.repo.source_started(source)
                try:
                    fresh, _ = await self.release_service.refresh(provider, external_id, media_format)
                    if fresh is None:
                        raise RuntimeError("Provider returned no metadata for tracked title")
                    await self.repo.source_succeeded(source)
                    checked += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self.repo.source_failed(source, type(exc).__name__)
                    errors += 1
                    log.warning(
                        "Check failed for provider %s (format %s, title ID %s): %s: %s",
                        source, media_format, external_id, type(exc).__name__, str(exc)[:240],
                    )
            try:
                await self.news_service.poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.repo.source_failed("RSS", type(exc).__name__)
                errors += 1
            sent = await self.notifications.dispatch_pending()
            result = {"checked": checked, "errors": errors, "notifications": sent}
            self.last_cycle = result
            self.last_cycle_at = int(time.time())
            return result

    async def refresh_one(self, provider: str, external_id: str, media_format: str) -> tuple[object, list[object]]:
        async with self._run_lock:
            await self.repo.source_started(provider)
            try:
                result = await self.release_service.refresh(provider, external_id, media_format)
                if result[0] is None:
                    raise RuntimeError("No metadata returned by provider")
                await self.repo.source_succeeded(provider)
                await self.notifications.dispatch_pending()
                return result
            except Exception as exc:
                await self.repo.source_failed(provider, type(exc).__name__)
                raise
