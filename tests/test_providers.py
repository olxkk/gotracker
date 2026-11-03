import pytest
from bot.providers.anilist import _from_anilist
from bot.providers.kitsu import _from_kitsu
from bot.providers.myanimelist import _from_mal
from bot.services.release_service import ProviderRegistry


def test_anilist_unknown_airing_is_none_not_fake_date():
    media = _from_anilist({"id": 1, "type": "MANGA", "title": {"romaji": "Example"}, "chapters": None, "nextAiringEpisode": None})
    assert media.title == "Example"
    assert media.next_airing_at is None
    assert media.chapters is None


def test_kitsu_and_mal_normalize_metadata():
    kitsu = _from_kitsu({"id": "7", "attributes": {"canonicalTitle": "Kitsu title", "chapterCount": None}}, "MANGA")
    mal = _from_mal({"id": 8, "title": "MAL title", "num_episodes": 12}, "ANIME")
    assert kitsu.title == "Kitsu title" and kitsu.chapters is None
    assert mal.title == "MAL title" and mal.episodes == 12


class FakeProvider:
    def __init__(self, name, results=None, error=None):
        self.name, self.results, self.error = name, results or [], error
    async def search(self, query, media_format="ANIME", limit=8):
        if self.error: raise self.error
        return self.results[:limit]
    async def get(self, external_id, media_format="ANIME"):
        return None


@pytest.mark.asyncio
async def test_search_falls_back_when_primary_api_fails():
    expected = _from_kitsu({"id": "1", "attributes": {"canonicalTitle": "Fallback"}}, "ANIME")
    providers = ProviderRegistry(FakeProvider("anilist", error=RuntimeError("429")), FakeProvider("kitsu", [expected]), FakeProvider("myanimelist"))
    results = await providers.search("Fallback", "ANIME")
    assert len(results) == 1 and results[0].provider == "kitsu"



@pytest.mark.asyncio
async def test_bounded_reader_waits_for_complete_response_body():
    from bot.providers.base import read_limited

    class Content:
        async def iter_chunked(self, size):
            yield b'{"data":'
            yield b'{"ok":true}}'

    class Response:
        content = Content()

    assert await read_limited(Response(), 64) == b'{"data":{"ok":true}}'


@pytest.mark.asyncio
async def test_bounded_reader_rejects_oversized_response():
    from bot.providers.base import read_limited

    class Content:
        async def iter_chunked(self, size):
            yield b"1234"
            yield b"5678"

    class Response:
        content = Content()

    with pytest.raises(ValueError, match="size limit"):
        await read_limited(Response(), 5)


@pytest.mark.asyncio
async def test_default_anime_search_uses_mal_before_fallbacks():
    mal_title = _from_mal({"id": 101, "title": "Primary MAL"}, "ANIME")
    kitsu_title = _from_kitsu({"id": "202", "attributes": {"canonicalTitle": "Fallback Kitsu"}}, "ANIME")
    anilist_title = _from_anilist({"id": 303, "type": "ANIME", "title": {"romaji": "Last fallback"}})
    providers = ProviderRegistry(
        FakeProvider("anilist", [anilist_title]),
        FakeProvider("kitsu", [kitsu_title]),
        FakeProvider("myanimelist", [mal_title]),
    )
    results = await providers.search("title", "ANIME", limit=10)
    assert [item.provider for item in results] == ["myanimelist", "kitsu", "anilist"]


@pytest.mark.asyncio
async def test_default_manga_search_uses_mangadex_before_catalogue_fallbacks():
    manga = MediaTitle("mangadex", "00000000-0000-4000-8000-000000000001",
                       "MangaDex primary", "MANGA", "https://mangadex.org/title/00000000-0000-4000-8000-000000000001")
    kitsu_title = _from_kitsu({"id": "202", "attributes": {"canonicalTitle": "Kitsu fallback"}}, "MANGA")
    anilist_title = _from_anilist({"id": 303, "type": "MANGA", "title": {"romaji": "AniList fallback"}})
    class MangaDexFake(FakeProvider):
        pass
    providers = ProviderRegistry(
        FakeProvider("anilist", [anilist_title]),
        FakeProvider("kitsu", [kitsu_title]),
        FakeProvider("myanimelist"),
        MangaDexFake("mangadex", [manga]),
    )
    results = await providers.search("title", "MANGA", limit=10)
    assert [item.provider for item in results] == ["mangadex", "kitsu", "anilist"]


def test_mal_currently_airing_status_normalizes_to_releasing():
    media = _from_mal({"id": 42, "title": "Airing", "status": "currently_airing"}, "ANIME")
    assert media.provider == "myanimelist"
    assert media.status == "RELEASING"
