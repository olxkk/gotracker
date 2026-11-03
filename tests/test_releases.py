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



@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anilist", "kitsu", "myanimelist"])
@pytest.mark.parametrize("media_format,field,old_count,new_count,event_type", [
    ("ANIME", "episodes", 12, 13, "new_episode"),
    ("MANGA", "chapters", 84, 85, "new_chapter"),
])
async def test_catalogue_count_increase_is_reported_once(repo, provider, media_format, field, old_count, new_count, event_type):
    old = MediaTitle(provider, "501", "Progress Test", media_format, "https://example.test/title")
    setattr(old, field, old_count)
    await repo.add_track(7, old)
    fresh = MediaTitle(provider, "501", "Progress Test", media_format, "https://example.test/title")
    setattr(fresh, field, new_count)
    registry = ProviderRegistry(
        FakeProvider("anilist", media=fresh if provider == "anilist" else None),
        FakeProvider("kitsu", media=fresh if provider == "kitsu" else None),
        FakeProvider("myanimelist", media=fresh if provider == "myanimelist" else None),
    )
    service = ReleaseService(repo, registry)
    refreshed, events = await service.refresh(provider, "501", media_format)
    assert refreshed is not None
    assert len(events) == 1
    assert events[0].update_type == event_type
    assert events[0].status == "unverified"
    assert events[0].release_at is None
    _, repeated = await service.refresh(provider, "501", media_format)
    assert repeated == []


@pytest.mark.asyncio
async def test_mangadex_chapter_feed_failure_is_not_silently_saved(repo):
    class BrokenMangaDex(FakeProvider):
        async def latest_english_chapter(self, external_id):
            raise TimeoutError("feed timeout")

    old = MediaTitle("mangadex", "00000000-0000-4000-8000-000000000001", "Feed Test", "MANGA",
                     "https://mangadex.org/title/00000000-0000-4000-8000-000000000001", chapters=8)
    await repo.add_track(7, old)
    fresh = MediaTitle("mangadex", old.external_id, "Feed Test", "MANGA", old.url, chapters=None)
    broken = BrokenMangaDex("mangadex", media=fresh)
    registry = ProviderRegistry(FakeProvider("anilist"), FakeProvider("kitsu"), FakeProvider("myanimelist"), broken)
    service = ReleaseService(repo, registry)
    with pytest.raises(TimeoutError):
        await service.refresh("mangadex", old.external_id, "MANGA")
    saved = await repo.get_media("mangadex", old.external_id)
    assert saved["chapters"] == 8
