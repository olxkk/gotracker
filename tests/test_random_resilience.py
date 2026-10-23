import pytest

from bot.providers.anilist import AniListProvider


@pytest.mark.asyncio
async def test_random_anime_skips_one_malformed_page_and_uses_next(monkeypatch):
    provider = AniListProvider(session=None)
    calls = 0

    async def fake_graphql(query, variables):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("AniList returned invalid JSON after retries")
        return {"Page": {"media": [{
            "id": 123, "type": "ANIME", "status": "RELEASING", "averageScore": 80,
            "episodes": 12, "genres": ["Action"], "title": {"english": "Example Anime"},
            "siteUrl": "https://anilist.co/anime/123", "coverImage": {"large": ""},
            "startDate": {"year": 2026}, "endDate": {}, "nextAiringEpisode": {},
        }]}}

    monkeypatch.setattr(provider, "_graphql", fake_graphql)
    result = await provider.random_anime("RELEASING")
    assert result is not None
    media, score = result
    assert media.title == "Example Anime"
    assert score == 80
    assert calls == 2
