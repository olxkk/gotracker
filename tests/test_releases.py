import time
import pytest
from bot.providers.base import MediaTitle
from bot.services.release_service import ProviderRegistry, ReleaseService


class FakeProvider:
    def __init__(self, name, media=None, search_results=None, error=None):
        self.name, self.media = name, media
        self.search_results = search_results or []
        self.error = error

    async def search(self, query, media_format="ANIME", limit=8):
        if self.error:
            raise self.error
        return self.search_results[:limit]

    async def get(self, external_id, media_format="ANIME"):
        if self.error:
            raise self.error
        return self.media


@pytest.mark.asyncio
async def test_detects_schedule_change_once_and_deduplicates(repo):
    now = int(time.time())
    baseline = MediaTitle("anilist", "10", "Test Anime", "ANIME", "https://anilist.co/anime/10", next_airing_at=now + 3600, next_episode=4)
    await repo.add_track(7, baseline)
    changed = MediaTitle("anilist", "10", "Test Anime", "ANIME", "https://anilist.co/anime/10", next_airing_at=now + 7200, next_episode=4)
    anilist = FakeProvider("anilist", media=changed)
    registry = ProviderRegistry(anilist, FakeProvider("kitsu"), FakeProvider("myanimelist"))
    service = ReleaseService(repo, registry)
    media, events = await service.refresh("anilist", "10", "ANIME")
    assert media is not None
    assert {item.update_type for item in events} == {"delay"}
    assert len(await repo.get_events("anilist", "10", 10)) == 1
    _, repeat_events = await service.refresh("anilist", "10", "ANIME")
    assert repeat_events == []
    assert len(await repo.get_events("anilist", "10", 10)) == 1


@pytest.mark.asyncio
async def test_unknown_manga_chapter_date_is_not_invented(repo):
    manga = MediaTitle("anilist", "20", "Manga Test", "MANGA", "https://anilist.co/manga/20", chapters=84)
    await repo.add_track(7, manga)
    registry = ProviderRegistry(FakeProvider("anilist", media=manga), FakeProvider("kitsu"), FakeProvider("myanimelist"))
    service = ReleaseService(repo, registry)
    refreshed, events = await service.refresh("anilist", "20", "MANGA")
    assert refreshed.chapters == 84
    assert refreshed.next_airing_at is None
    assert events == []
    assert await repo.get_events("anilist", "20") == []


@pytest.mark.asyncio
async def test_provider_failure_bubbles_for_health_tracking(repo):
    media = MediaTitle("anilist", "30", "Unavailable", "ANIME", "https://anilist.co/anime/30")
    await repo.add_track(7, media)
    registry = ProviderRegistry(FakeProvider("anilist", error=RuntimeError("429")), FakeProvider("kitsu"), FakeProvider("myanimelist"))
    service = ReleaseService(repo, registry)
    with pytest.raises(RuntimeError):
        await service.refresh("anilist", "30", "ANIME")


@pytest.mark.asyncio
async def test_conflicting_catalogue_sources_are_not_merged(repo):
    now = int(time.time())
    primary = MediaTitle("anilist", "70", "Conflicted Title", "ANIME", "https://anilist.co/anime/70", next_airing_at=now + 3600, next_episode=2)
    secondary = MediaTitle("kitsu", "80", "Conflicted Title", "ANIME", "https://kitsu.io/anime/80", next_airing_at=None, next_episode=None)
    providers = ProviderRegistry(FakeProvider("anilist", search_results=[primary]), FakeProvider("kitsu", search_results=[secondary]), FakeProvider("myanimelist"))
    results = await providers.search("Conflicted Title", "ANIME", limit=5)
    assert results[0].provider == "anilist"
    assert results[0].next_airing_at == now + 3600
    assert results[1].provider == "kitsu"
    assert results[1].next_airing_at is None  # metadata from Kitsu did not overwrite AniList's schedule
