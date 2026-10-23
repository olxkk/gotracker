import time
import pytest
import discord
from bot.providers.base import MediaTitle, ReleaseItem
from bot.services.notification_service import NotificationService


class FakeMessage:
    id = 555


class FakeChannel:
    def __init__(self):
        self.sent = []
    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return FakeMessage()


class FakeClient:
    def __init__(self, channel):
        self.channel = channel
    def get_channel(self, channel_id):
        return self.channel if channel_id == 99 else None
    async def fetch_channel(self, channel_id):
        if channel_id == 99:
            return self.channel
        raise discord.NotFound(response=None, message="not found")


@pytest.mark.asyncio
async def test_notification_deduplication_per_guild(repo):
    media = MediaTitle("anilist", "55", "Test", "ANIME", "https://anilist.co/anime/55")
    await repo.add_track(1, media)
    await repo.add_track(2, media)
    await repo.set_guild_setting(1, "notification_channel_id", 99)
    await repo.set_guild_setting(2, "notification_channel_id", 99)
    event = ReleaseItem("key-unique", "Test", "ANIME", "upcoming_episode", 10, int(time.time()) + 200,
                        "scheduled", "AniList", "https://anilist.co/anime/55", "Scheduled", False)
    await repo.add_release(event, "anilist", "55")
    channel = FakeChannel()
    service = NotificationService(repo, FakeClient(channel))
    first = await service.dispatch_pending()
    second = await service.dispatch_pending()
    assert first == 2
    assert second == 0
    assert len(channel.sent) == 2


def test_allowed_mentions_none_role_user_and_everyone_are_explicit(repo):
    # These tests use the service's pure routing policy without a Discord connection.
    service = NotificationService(repo, FakeClient(FakeChannel()))
    content, mentions = service._mention_payload({"default_target": "none"}, {"summary": "@everyone"})
    assert content is None and mentions.everyone is False and mentions.users is False and mentions.roles is False
    content, mentions = service._mention_payload({"default_target": "role", "target_role_id": 123}, None)
    assert content == "<@&123>" and mentions.roles == [discord.Object(id=123)] and mentions.everyone is False
    content, mentions = service._mention_payload({"default_target": "user", "target_user_id": 456}, None)
    assert content == "<@456>" and mentions.users == [discord.Object(id=456)] and mentions.everyone is False
    content, mentions = service._mention_payload({"default_target": "everyone", "everyone_enabled": 1}, None)
    assert content == "@everyone" and mentions.everyone is True and mentions.users is False
    content, mentions = service._mention_payload({"default_target": "everyone", "everyone_enabled": 0}, None)
    assert content is None and mentions.everyone is False


@pytest.mark.asyncio
async def test_unknown_release_date_remains_unknown_in_database(repo):
    media = MediaTitle("anilist", "56", "Manga", "MANGA", "https://anilist.co/manga/56", chapters=40)
    await repo.add_track(3, media)
    event = ReleaseItem("unknown-date", "Manga", "MANGA", "news_report", None, None, "unverified", "RSS", "https://example.org/news", "Date unknown", False)
    await repo.add_release(event, "anilist", "56")
    row = (await repo.get_events("anilist", "56"))[0]
    assert row["release_at"] is None and row["status"] == "unverified"

@pytest.mark.asyncio
async def test_category_route_and_title_override_are_isolated(repo):
    media = MediaTitle("anilist", "88", "One Piece", "ANIME", "https://anilist.co/anime/88")
    await repo.add_track(11, media)
    await repo.add_track(12, media)
    await repo.set_notification_route(11, "episodes", 101, target_mode="role", role_id=501)
    category = await repo.get_notification_route(11, "episodes", provider="anilist", external_id="88")
    assert category["channel_id"] == 101
    assert category["target_mode"] == "role" and category["role_id"] == 501
    await repo.set_notification_route(11, "episodes", 102, provider="anilist", external_id="88", target_mode="none")
    title = await repo.get_notification_route(11, "episodes", provider="anilist", external_id="88")
    other_server = await repo.get_notification_route(12, "episodes", provider="anilist", external_id="88")
    assert title["scope"] == "title" and title["channel_id"] == 102 and title["target_mode"] == "none"
    assert other_server is None
    await repo.delete_notification_route(11, "episodes", provider="anilist", external_id="88")
    fallback = await repo.get_notification_route(11, "episodes", provider="anilist", external_id="88")
    assert fallback["scope"] == "category" and fallback["channel_id"] == 101


@pytest.mark.asyncio
async def test_everyone_route_requires_explicit_enable(repo):
    media = MediaTitle("anilist", "89", "Example", "ANIME", "https://anilist.co/anime/89")
    await repo.add_track(21, media)
    with pytest.raises(ValueError, match="explicitly enabled"):
        await repo.set_notification_route(21, "news", 303, target_mode="everyone", everyone_enabled=False)
    await repo.set_notification_route(21, "news", 303, target_mode="everyone", everyone_enabled=True)
    route = await repo.get_notification_route(21, "news")
    assert route["target_mode"] == "everyone" and route["everyone_enabled"] == 1


@pytest.mark.asyncio
async def test_title_preview_uses_title_specific_channel_and_role(repo):
    media = MediaTitle("anilist", "777", "Example Show", "ANIME", "https://anilist.co/anime/777")
    await repo.add_track(31, media)
    await repo.set_guild_setting(31, "notification_channel_id", 88)
    await repo.set_notification_route(31, "episodes", 99, provider="anilist", external_id="777",
                                      target_mode="role", role_id=501)
    track = await repo.get_track(31, "anilist", "777")
    channel = FakeChannel()
    service = NotificationService(repo, FakeClient(channel))

    success, message = await service.preview_title(31, track)

    assert success is True
    assert "title-specific route" in message
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"] == "<@&501>"
    assert channel.sent[0]["allowed_mentions"].roles == [discord.Object(id=501)]
    assert "No new episode or chapter" in channel.sent[0]["embed"].description


@pytest.mark.asyncio
async def test_title_preview_does_not_send_when_title_notifications_disabled(repo):
    media = MediaTitle("anilist", "778", "Muted Show", "ANIME", "https://anilist.co/anime/778")
    await repo.add_track(32, media)
    await repo.update_track_setting(32, "anilist", "778", "notifications_enabled", False)
    track = await repo.get_track(32, "anilist", "778")
    channel = FakeChannel()
    service = NotificationService(repo, FakeClient(channel))

    success, message = await service.preview_title(32, track)

    assert success is False
    assert "disabled for notifications" in message
    assert channel.sent == []
