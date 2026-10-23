import pytest
from bot.providers.base import MediaTitle


@pytest.mark.asyncio
async def test_add_remove_title_and_prevent_duplicates(repo):
    media = MediaTitle("anilist", "101", "One Piece", "ANIME", "https://anilist.co/anime/101")
    inserted, row_id = await repo.add_track(11, media)
    assert inserted is True and row_id
    duplicate, duplicate_id = await repo.add_track(11, media)
    assert duplicate is False and duplicate_id == row_id
    assert len(await repo.list_tracks(11)) == 1
    assert await repo.remove_track(11, str(row_id)) == 1
    assert await repo.list_tracks(11) == []


@pytest.mark.asyncio
async def test_server_watchlists_and_settings_are_isolated(repo):
    anime = MediaTitle("anilist", "102", "Solo Leveling", "ANIME", "https://anilist.co/anime/102")
    manga = MediaTitle("anilist", "202", "Solo Leveling", "MANGA", "https://anilist.co/manga/202", chapters=200)
    await repo.add_track(111, anime)
    await repo.add_track(222, manga)
    await repo.set_guild_setting(111, "default_target", "role")
    await repo.set_guild_setting(111, "target_role_id", 123456)
    await repo.set_guild_setting(222, "default_target", "none")
    assert [row["format"] for row in await repo.list_tracks(111)] == ["ANIME"]
    assert [row["format"] for row in await repo.list_tracks(222)] == ["MANGA"]
    assert (await repo.get_guild(111))["target_role_id"] == 123456
    assert (await repo.get_guild(222))["target_role_id"] is None


@pytest.mark.asyncio
async def test_persistence_across_database_reopen(tmp_path):
    path = str(tmp_path / "persistent.sqlite3")
    db = __import__("bot.database.session", fromlist=["Database"]).Database(path)
    await db.connect()
    repo = __import__("bot.database.repositories", fromlist=["Repository"]).Repository(db)
    media = MediaTitle("anilist", "303", "Frieren", "ANIME", "https://anilist.co/anime/303", next_airing_at=1999999999, next_episode=2)
    await repo.add_track(5, media)
    await repo.set_guild_setting(5, "notification_channel_id", 98765)
    await db.close()

    db2 = __import__("bot.database.session", fromlist=["Database"]).Database(path)
    await db2.connect()
    repo2 = __import__("bot.database.repositories", fromlist=["Repository"]).Repository(db2)
    rows = await repo2.list_tracks(5)
    assert len(rows) == 1 and rows[0]["title"] == "Frieren"
    assert (await repo2.get_guild(5))["notification_channel_id"] == 98765
    await db2.close()


@pytest.mark.asyncio
async def test_ambiguous_same_title_is_not_silently_removed(repo):
    first = MediaTitle("anilist", "1", "Naruto", "ANIME", "https://anilist.co/anime/1")
    second = MediaTitle("kitsu", "1", "Naruto", "MANGA", "https://kitsu.io/manga/1")
    await repo.add_track(50, first)
    await repo.add_track(50, second)
    matches = await repo.resolve_tracks(50, "Naruto")
    exact = [row for row in matches if row["title"].casefold() == "naruto"]
    assert len(exact) == 2
    assert await repo.remove_track(50, "Naruto") == 0
    assert len(await repo.list_tracks(50)) == 2


@pytest.mark.asyncio
async def test_cross_provider_duplicate_is_blocked_but_anime_and_manga_are_distinct(repo):
    anime_anilist = MediaTitle("anilist", "777", "Same Name", "ANIME", "https://anilist.co/anime/777")
    anime_kitsu = MediaTitle("kitsu", "888", "Same Name", "ANIME", "https://kitsu.io/anime/888")
    manga = MediaTitle("anilist", "999", "Same Name", "MANGA", "https://anilist.co/manga/999")
    inserted, _ = await repo.add_track(9, anime_anilist)
    assert inserted
    duplicate, existing_id = await repo.add_track(9, anime_kitsu)
    assert not duplicate and existing_id
    manga_inserted, _ = await repo.add_track(9, manga)
    assert manga_inserted
    assert [(row['format'], row['provider']) for row in await repo.list_tracks(9)] == [('ANIME', 'anilist'), ('MANGA', 'anilist')]
