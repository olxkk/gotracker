import pytest

from bot.providers.base import MediaTitle


@pytest.mark.asyncio
async def test_explicit_mangadex_selection_migrates_existing_anilist_manga_and_keeps_routes(repo):
    anilist = MediaTitle(provider="anilist", external_id="210482", title="Example Manga", format="MANGA", url="https://anilist.co/manga/210482")
    mangadex = MediaTitle(provider="mangadex", external_id="12345678-1234-1234-1234-123456789abc", title="Example Manga", format="MANGA", url="https://mangadex.org/title/12345678-1234-1234-1234-123456789abc")

    inserted, tracked_id = await repo.add_track(123, anilist)
    assert inserted is True
    await repo.set_notification_route(123, "chapters", 456, provider="anilist", external_id="210482", target_mode="role", role_id=789)

    migrated, same_id = await repo.add_track(123, mangadex)
    assert migrated is True
    assert same_id == tracked_id

    tracks = await repo.list_tracks(123)
    assert len(tracks) == 1
    assert tracks[0]["provider"] == "mangadex"
    assert tracks[0]["external_id"] == mangadex.external_id

    route = await repo.db.fetchone("SELECT * FROM title_notification_routes WHERE guild_id=? AND provider=? AND external_id=? AND category=?", (123, "mangadex", mangadex.external_id, "chapters"))
    assert route is not None
    assert route["channel_id"] == 456
    assert route["role_id"] == 789


@pytest.mark.asyncio
async def test_default_manga_search_prefers_mangadex():
    from bot.services.release_service import ProviderRegistry

    class FakeProvider:
        def __init__(self, media):
            self.media = media
        async def search(self, query, media_format="MANGA", limit=8):
            return [self.media]
        async def get(self, external_id, media_format="MANGA"):
            return self.media if external_id == self.media.external_id else None

    md = MediaTitle(provider="mangadex", external_id="12345678-1234-1234-1234-123456789abc", title="Manga", format="MANGA", url="https://mangadex.org/title/12345678-1234-1234-1234-123456789abc")
    anilist = MediaTitle(provider="anilist", external_id="210482", title="Manga", format="MANGA", url="https://anilist.co/manga/210482")
    registry = ProviderRegistry(FakeProvider(anilist), FakeProvider(anilist), FakeProvider(anilist), FakeProvider(md))
    result = await registry.search("Manga", "MANGA")
    assert len(result) == 1 and result[0].provider == "mangadex"


@pytest.mark.asyncio
async def test_mangadex_anilist_cross_reference_migrates_different_title_spelling(repo):
    anilist = MediaTitle(provider="anilist", external_id="210482", title="Original AniList title", format="MANGA", url="https://anilist.co/manga/210482")
    mangadex = MediaTitle(provider="mangadex", external_id="abcdefab-1234-1234-1234-123456789abc", title="Localized MangaDex title", format="MANGA", url="https://mangadex.org/title/abcdefab-1234-1234-1234-123456789abc", external_ids={"anilist": "210482"})
    await repo.add_track(321, anilist)
    migrated, _ = await repo.add_track(321, mangadex)
    assert migrated is True
    tracks = await repo.list_tracks(321)
    assert len(tracks) == 1
    assert tracks[0]["provider"] == "mangadex"
    assert tracks[0]["title"] == "Localized MangaDex title"


@pytest.mark.asyncio
async def test_existing_mangadex_entry_cleans_up_older_anilist_duplicate(repo):
    anilist = MediaTitle(provider="anilist", external_id="210482", title="Original AniList title", format="MANGA", url="https://anilist.co/manga/210482")
    md_without_mapping = MediaTitle(provider="mangadex", external_id="abcdefab-1234-1234-1234-123456789abc", title="Localized MangaDex title", format="MANGA", url="https://mangadex.org/title/abcdefab-1234-1234-1234-123456789abc")
    md_with_mapping = MediaTitle(provider="mangadex", external_id=md_without_mapping.external_id, title=md_without_mapping.title, format="MANGA", url=md_without_mapping.url, external_ids={"anilist": "210482"})
    await repo.add_track(654, anilist)
    await repo.add_track(654, md_without_mapping)
    inserted, _ = await repo.add_track(654, md_with_mapping)
    assert inserted is False
    tracks = await repo.list_tracks(654)
    assert len(tracks) == 1
    assert tracks[0]["provider"] == "mangadex"
