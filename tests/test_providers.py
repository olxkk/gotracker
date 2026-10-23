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
