import pytest
import time
from bot.providers.base import MediaTitle, NewsItem
from bot.services.news_service import NewsService


class FakeRSSProvider:
    name = "Fake RSS"
    feeds = [("Test Feed", "https://example.org/feed.xml", False)]
    last_errors = []
    def __init__(self): self.items = []
    async def fetch(self): return list(self.items)


@pytest.mark.asyncio
async def test_rss_baseline_avoids_backlog_then_detects_new_title_news(repo):
    media = MediaTitle("anilist", "61", "One Piece", "ANIME", "https://anilist.co/anime/61")
    await repo.add_track(777, media)
    rss = FakeRSSProvider()
    rss.items = [NewsItem("old-entry", "One Piece season 2 report", "Existing feed history", "https://example.org/old", "Test Feed", int(time.time()) - 10, False)]
    service = NewsService(repo, rss)

    assert await service.poll() == 0  # First fetch seeds old items without notifying.
    assert await repo.get_events("anilist", "61") == []

    rss.items.append(NewsItem("new-entry", "One Piece delayed", "The schedule has changed", "https://example.org/new", "Test Feed", int(time.time()), False))
    assert await service.poll() == 1
    events = await repo.get_events("anilist", "61")
    assert len(events) == 1
    assert events[0]["update_type"] == "delay"
    assert events[0]["status"] == "unverified"

    assert await service.poll() == 0
    assert len(await repo.get_events("anilist", "61")) == 1


@pytest.mark.asyncio
async def test_newly_added_feed_is_baselined_independently(repo):
    rss = FakeRSSProvider()
    service = NewsService(repo, rss)
    await repo.add_track(777, MediaTitle("anilist", "61", "One Piece", "ANIME", "https://anilist.co/anime/61"))
    await service.poll()
    await repo.source_succeeded("RSS:Test Feed")
    # Simulate configuring a new feed name after the bot has already been running.
    rss.feeds = [("New Feed", "https://example.org/new.xml", True)]
    rss.items = [NewsItem("archive", "One Piece new season", "Old announcement", "https://example.org/archive", "New Feed", int(time.time()) - 10, True)]
    assert await service.poll() == 0
    assert await repo.get_events("anilist", "61") == []
    rss.items.append(NewsItem("new", "One Piece season 2 announced", "New article", "https://example.org/new", "New Feed", int(time.time()), True))
    assert await service.poll() == 1
    events = await repo.get_events("anilist", "61")
    assert len(events) == 1 and events[0]["update_type"] == "new_season"
