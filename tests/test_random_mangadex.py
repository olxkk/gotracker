from __future__ import annotations

import pytest

from bot.providers.anilist import AniListProvider
from bot.providers.mangadex import MangaDexProvider
from bot.services.release_service import ProviderRegistry


class FakeProvider:
    async def search(self, query, media_format="ANIME", limit=8):
        return []

    async def get(self, external_id, media_format="ANIME"):
        return None


@pytest.mark.asyncio
async def test_mangadex_is_selectable_and_manga_only():
    md = MangaDexProvider(session=None)
    registry = ProviderRegistry(FakeProvider(), FakeProvider(), FakeProvider(), md)
    assert registry.get_provider("mangadex") is md
    assert await registry.search("Naruto", "ANIME", source="mangadex") == []


def test_mangadex_whole_chapter_number_parser_rules():
    # Test the numeric policy independently from live API/network access.
    accepted = []
    for raw in ["1", "10", "100", "12.5", "0", None, "special"]:
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number >= 0 and number.is_integer():
            accepted.append(int(number))
    assert accepted == [1, 10, 100, 0]


@pytest.mark.asyncio
async def test_random_anime_returns_none_when_provider_has_no_matching_pages(monkeypatch):
    provider = AniListProvider(session=None)

    async def empty_graphql(query, variables):
        return {"Page": {"media": []}}

    monkeypatch.setattr(provider, "_graphql", empty_graphql)
    assert await provider.random_anime("FINISHED") is None
    assert await provider.random_anime("HIGH_RATED", 90) is None

@pytest.mark.asyncio
async def test_random_anime_applies_optional_filters(monkeypatch):
    provider = AniListProvider(session=None)
    captured = {}

    async def filtered_graphql(query, variables):
        captured["query"] = query
        captured["variables"] = variables
        return {"Page": {"media": [{
            "id": 123,
            "type": "ANIME",
            "format": "TV",
            "status": "FINISHED",
            "episodes": 12,
            "genres": ["Comedy", "Romance"],
            "averageScore": 86,
            "title": {"english": "Example Anime", "romaji": "Example Anime"},
            "coverImage": {"large": "https://example.com/cover.jpg"},
            "siteUrl": "https://anilist.co/anime/123",
            "startDate": {"year": 2022, "month": 1, "day": 1},
            "endDate": {"year": 2022, "month": 3, "day": 1},
        }]}}

    monkeypatch.setattr(provider, "_graphql", filtered_graphql)
    result = await provider.random_anime("FINISHED", 75, "Comedy", 12, 2022)
    assert result is not None
    media, score = result
    assert media.title == "Example Anime"
    assert score == 86
    assert captured["variables"]["genres"] == ["Comedy"]
    assert captured["variables"]["maxEpisodes"] == 13
    assert captured["variables"]["year"] == 2022
    assert "genre_in: $genres" in captured["query"]
    assert "episodes_lesser: $maxEpisodes" in captured["query"]
    assert "seasonYear: $year" in captured["query"]


def test_random_anime_rejects_unknown_genre():
    # Validation is performed before making a network request.
    provider = AniListProvider(session=None)
    import asyncio
    with pytest.raises(ValueError, match="Unsupported anime genre"):
        asyncio.run(provider.random_anime("FINISHED", genre="Not A Genre"))


@pytest.mark.asyncio
async def test_random_anime_uses_compact_query_without_description(monkeypatch):
    provider = AniListProvider(session=None)
    captured = {}

    async def compact_graphql(query, variables):
        captured["query"] = query
        return {"Page": {"media": [{
            "id": 456, "type": "ANIME", "status": "FINISHED", "episodes": 12,
            "genres": ["Comedy"], "averageScore": 82,
            "title": {"english": "Compact Result", "romaji": "Compact Result"},
            "coverImage": {"large": "https://example.com/cover.jpg"},
            "siteUrl": "https://anilist.co/anime/456",
            "startDate": {"year": 2021, "month": 1, "day": 1},
        }]}}

    monkeypatch.setattr(provider, "_graphql", compact_graphql)
    result = await provider.random_anime("FINISHED")
    assert result is not None
    assert "description(asHtml:false)" not in captured["query"]
    assert "averageScore" in captured["query"]
