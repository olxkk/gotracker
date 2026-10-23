from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .session import Database
from ..providers.base import MediaTitle, ReleaseItem


def now_utc() -> int:
    return int(time.time())


class Repository:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_guild(self, guild_id: int) -> dict[str, Any]:
        now = now_utc()
        async with self.db.transaction() as conn:
            await conn.execute("INSERT INTO guild_settings(guild_id,created_at,updated_at) VALUES(?,?,?) ON CONFLICT(guild_id) DO NOTHING", (guild_id, now, now))
        return await self.get_guild(guild_id) or {}

    async def get_guild(self, guild_id: int) -> dict[str, Any] | None:
        return await self.db.fetchone("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,))

    async def set_guild_setting(self, guild_id: int, field: str, value: Any) -> None:
        allowed = {"notification_channel_id", "default_target", "target_role_id", "target_user_id", "everyone_enabled", "timezone", "quiet_start", "quiet_end"}
        if field not in allowed:
            raise ValueError("Unsupported server setting")
        await self.ensure_guild(guild_id)
        await self.db.execute(f"UPDATE guild_settings SET {field}=?,updated_at=? WHERE guild_id=?", (value, now_utc(), guild_id))

    async def save_media(self, media: MediaTitle, checked_at: int | None = None) -> None:
        now = now_utc()
        await self.db.execute(
            """INSERT INTO media(provider,external_id,title,format,url,cover_url,description,status,episodes,chapters,next_airing_at,next_episode,start_date,end_date,last_checked_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(provider,external_id) DO UPDATE SET title=excluded.title,format=excluded.format,url=excluded.url,
               cover_url=excluded.cover_url,description=excluded.description,status=excluded.status,episodes=excluded.episodes,
               chapters=excluded.chapters,next_airing_at=excluded.next_airing_at,next_episode=excluded.next_episode,
               start_date=excluded.start_date,end_date=excluded.end_date,last_checked_at=excluded.last_checked_at,updated_at=excluded.updated_at""",
            (media.provider, media.external_id, media.title, media.format, media.url, media.cover_url, media.description, media.status,
             media.episodes, media.chapters, media.next_airing_at, media.next_episode, media.start_date, media.end_date, checked_at or now, now),
        )

    async def get_media(self, provider: str, external_id: str) -> dict[str, Any] | None:
        return await self.db.fetchone("SELECT * FROM media WHERE provider=? AND external_id=?", (provider, str(external_id)))

    async def add_track(self, guild_id: int, media: MediaTitle) -> tuple[bool, int | None]:
        """Returns (inserted, tracked_title_id); duplicate titles return (False, existing id)."""
        now = now_utc()
        await self.ensure_guild(guild_id)
        await self.save_media(media)
        async with self.db.transaction() as conn:
            existing_cursor = await conn.execute("SELECT id FROM tracked_titles WHERE guild_id=? AND provider=? AND external_id=?", (guild_id, media.provider, media.external_id))
            existing = await existing_cursor.fetchone()
            if existing:
                return False, int(existing[0])
            # A title is tracked once per server and format even when it is found through
            # multiple catalogue providers. Anime and manga with the same name remain distinct.
            duplicate_cursor = await conn.execute("SELECT id FROM tracked_titles WHERE guild_id=? AND format=? AND lower(title)=lower(?) ORDER BY id LIMIT 1", (guild_id, media.format, media.title.strip()))
            duplicate = await duplicate_cursor.fetchone()
            if duplicate:
                return False, int(duplicate[0])
            cursor = await conn.execute(
                "INSERT INTO tracked_titles(guild_id,provider,external_id,title,format,added_at) VALUES(?,?,?,?,?,?)",
                (guild_id, media.provider, media.external_id, media.title, media.format, now),
            )
            return True, cursor.lastrowid

    async def remove_track(self, guild_id: int, query: str) -> int:
        # Exact match on title, provider/id, or numeric tracked row id.
        async with self.db.transaction() as conn:
            if query.isdigit():
                cur = await conn.execute("DELETE FROM tracked_titles WHERE guild_id=? AND id=?", (guild_id, int(query)))
            else:
                exact = await conn.execute("SELECT id FROM tracked_titles WHERE guild_id=? AND (lower(title)=lower(?) OR lower(provider || ':' || external_id)=lower(?))", (guild_id, query.strip(), query.strip()))
                matches = await exact.fetchall()
                if len(matches) != 1:
                    return 0
                cur = await conn.execute("DELETE FROM tracked_titles WHERE guild_id=? AND id=?", (guild_id, int(matches[0][0])))
            return cur.rowcount

    async def list_tracks(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.db.fetchall(
            """SELECT t.*,m.url,m.cover_url,m.status,m.episodes,m.chapters,m.next_airing_at,m.next_episode,m.last_checked_at AS media_last_checked_at
            FROM tracked_titles t LEFT JOIN media m ON m.provider=t.provider AND m.external_id=t.external_id
            WHERE t.guild_id=? ORDER BY t.format,t.title COLLATE NOCASE""", (guild_id,)
        )

    async def get_track(self, guild_id: int, provider: str, external_id: str) -> dict[str, Any] | None:
        return await self.db.fetchone("""SELECT t.*,m.url,m.cover_url,m.description,m.status,m.episodes,m.chapters,m.next_airing_at,m.next_episode,m.start_date,m.end_date,m.last_checked_at AS media_last_checked_at
        FROM tracked_titles t LEFT JOIN media m ON m.provider=t.provider AND m.external_id=t.external_id
        WHERE t.guild_id=? AND t.provider=? AND t.external_id=?""", (guild_id, provider, str(external_id)))

    async def resolve_tracks(self, guild_id: int, title_query: str) -> list[dict[str, Any]]:
        return await self.db.fetchall("""SELECT t.*,m.url,m.cover_url,m.status,m.episodes,m.chapters,m.next_airing_at,m.next_episode
        FROM tracked_titles t LEFT JOIN media m ON m.provider=t.provider AND m.external_id=t.external_id
        WHERE t.guild_id=? AND lower(t.title) LIKE lower(?) ORDER BY t.title COLLATE NOCASE LIMIT 10""", (guild_id, f"%{title_query.strip()}%"))


    async def all_tracked_titles(self) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT t.*,m.url,m.cover_url,m.status,m.episodes,m.chapters,m.next_airing_at,m.next_episode FROM tracked_titles t LEFT JOIN media m ON m.provider=t.provider AND m.external_id=t.external_id ORDER BY t.guild_id,t.title COLLATE NOCASE")

    async def update_track_setting(self, guild_id: int, provider: str, external_id: str, field: str, value: Any) -> bool:
        allowed = {"notifications_enabled", "notify_episodes", "notify_chapters", "notify_schedule", "notify_delays", "notify_hiatus", "notify_announcements"}
        if field not in allowed:
            raise ValueError("Unsupported title notification setting")
        cur = await self.db.execute(f"UPDATE tracked_titles SET {field}=? WHERE guild_id=? AND provider=? AND external_id=?", (int(value) if field.startswith("notify_") or field == "notifications_enabled" else value, guild_id, provider, str(external_id)))
        return bool(cur)


    ROUTE_CATEGORIES = {"episodes", "chapters", "news", "schedule"}

    async def set_notification_route(self, guild_id: int, category: str, channel_id: int, *,
                                     provider: str | None = None, external_id: str | None = None,
                                     target_mode: str = "none", role_id: int | None = None,
                                     user_id: int | None = None, everyone_enabled: bool = False) -> None:
        if category not in self.ROUTE_CATEGORIES:
            raise ValueError("Unsupported notification category")
        if target_mode not in {"none", "role", "user", "everyone"}:
            raise ValueError("Unsupported notification target")
        if target_mode == "role" and role_id is None:
            raise ValueError("A role ID is required for role notifications")
        if target_mode == "user" and user_id is None:
            raise ValueError("A user ID is required for user notifications")
        if target_mode == "everyone" and not everyone_enabled:
            raise ValueError("@everyone must be explicitly enabled")
        await self.ensure_guild(guild_id)
        now = now_utc()
        if provider is None or external_id is None:
            await self.db.execute("""INSERT INTO guild_notification_routes
                (guild_id,category,channel_id,target_mode,role_id,user_id,everyone_enabled,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,category) DO UPDATE SET
                channel_id=excluded.channel_id,target_mode=excluded.target_mode,role_id=excluded.role_id,
                user_id=excluded.user_id,everyone_enabled=excluded.everyone_enabled,updated_at=excluded.updated_at""",
                (guild_id, category, channel_id, target_mode, role_id, user_id, int(everyone_enabled), now))
        else:
            if not await self.get_track(guild_id, provider, str(external_id)):
                raise ValueError("Track this title in this server before configuring a title-specific route")
            await self.db.execute("""INSERT INTO title_notification_routes
                (guild_id,provider,external_id,category,channel_id,target_mode,role_id,user_id,everyone_enabled,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,provider,external_id,category) DO UPDATE SET
                channel_id=excluded.channel_id,target_mode=excluded.target_mode,role_id=excluded.role_id,
                user_id=excluded.user_id,everyone_enabled=excluded.everyone_enabled,updated_at=excluded.updated_at""",
                (guild_id, provider, str(external_id), category, channel_id, target_mode, role_id, user_id, int(everyone_enabled), now))

    async def delete_notification_route(self, guild_id: int, category: str, *,
                                        provider: str | None = None, external_id: str | None = None) -> bool:
        if category not in self.ROUTE_CATEGORIES:
            raise ValueError("Unsupported notification category")
        if provider is None or external_id is None:
            return bool(await self.db.execute("DELETE FROM guild_notification_routes WHERE guild_id=? AND category=?", (guild_id, category)))
        return bool(await self.db.execute("DELETE FROM title_notification_routes WHERE guild_id=? AND provider=? AND external_id=? AND category=?", (guild_id, provider, str(external_id), category)))

    async def get_notification_route(self, guild_id: int, category: str, *,
                                     provider: str | None = None, external_id: str | None = None) -> dict[str, Any] | None:
        if provider is not None and external_id is not None:
            row = await self.db.fetchone("SELECT * FROM title_notification_routes WHERE guild_id=? AND provider=? AND external_id=? AND category=?",
                                         (guild_id, provider, str(external_id), category))
            if row:
                row["scope"] = "title"
                return row
        row = await self.db.fetchone("SELECT * FROM guild_notification_routes WHERE guild_id=? AND category=?", (guild_id, category))
        if row:
            row["scope"] = "category"
        return row

    async def list_notification_routes(self, guild_id: int) -> list[dict[str, Any]]:
        categories = await self.db.fetchall("SELECT *, 'category' AS scope FROM guild_notification_routes WHERE guild_id=?", (guild_id,))
        titles = await self.db.fetchall("""SELECT r.*, 'title' AS scope,t.title FROM title_notification_routes r
            JOIN tracked_titles t ON t.guild_id=r.guild_id AND t.provider=r.provider AND t.external_id=r.external_id
            WHERE r.guild_id=? ORDER BY t.title,r.category""", (guild_id,))
        return categories + titles

    async def add_release(self, event: ReleaseItem, provider: str, external_id: str) -> bool:
        cur = await self.db.execute(
            """INSERT INTO release_events(release_key,provider,external_id,title,format,update_type,number,release_at,status,source,url,summary,official,detected_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(release_key) DO NOTHING""",
            (event.release_key, provider, str(external_id), event.title, event.format, event.update_type, event.number, event.release_at,
             event.status, event.source, event.url, event.summary, int(event.official), now_utc()),
        )
        return bool(cur)

    async def get_events(self, provider: str, external_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM release_events WHERE provider=? AND external_id=? ORDER BY COALESCE(release_at,detected_at) DESC LIMIT ?", (provider, str(external_id), limit))

    async def upcoming_for_guild(self, guild_id: int, limit: int = 20) -> list[dict[str, Any]]:
        return await self.db.fetchall("""SELECT t.title,t.format,t.provider,t.external_id,m.url,m.next_airing_at,m.next_episode
        FROM tracked_titles t JOIN media m ON m.provider=t.provider AND m.external_id=t.external_id
        WHERE t.guild_id=? AND m.next_airing_at IS NOT NULL AND m.next_airing_at>=?
        ORDER BY m.next_airing_at LIMIT ?""", (guild_id, now_utc(), limit))

    async def list_pending_events(self, since: int, limit: int = 500) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM release_events WHERE detected_at>=? ORDER BY detected_at DESC LIMIT ?", (since, limit))

    async def list_guilds_tracking(self, provider: str, external_id: str) -> list[dict[str, Any]]:
        return await self.db.fetchall("""SELECT t.*,g.notification_channel_id,g.default_target,g.target_role_id,g.target_user_id,g.everyone_enabled,g.timezone,g.quiet_start,g.quiet_end
        FROM tracked_titles t JOIN guild_settings g ON g.guild_id=t.guild_id
        WHERE t.provider=? AND t.external_id=?""", (provider, str(external_id)))

    async def reserve_notification(self, guild_id: int, release_key: str, channel_id: int) -> bool:
        now = now_utc()
        # Retry known send failures sooner, but keep stale in-flight reservations longer
        # to reduce duplicate pings if the process crashed after Discord accepted a message.
        async with self.db.transaction() as conn:
            await conn.execute(
                "DELETE FROM notification_history WHERE guild_id=? AND release_key=? AND ((result='failed' AND sent_at<?) OR (result='pending' AND sent_at<?))",
                (guild_id, release_key, now - 120, now - 900),
            )
            cur = await conn.execute("INSERT INTO notification_history(guild_id,release_key,channel_id,sent_at,result) VALUES(?,?,?,?, 'pending') ON CONFLICT(guild_id,release_key) DO NOTHING", (guild_id, release_key, channel_id, now))
            return cur.rowcount > 0

    async def finish_notification(self, guild_id: int, release_key: str, result: str, message_id: int | None = None) -> None:
        await self.db.execute("UPDATE notification_history SET result=?,message_id=? WHERE guild_id=? AND release_key=?", (result, message_id, guild_id, release_key))

    async def mark_feed_item_seen(self, item_id: str, source: str) -> bool:
        cur = await self.db.execute("INSERT INTO seen_feed_items(item_id,source,seen_at) VALUES(?,?,?) ON CONFLICT(item_id) DO NOTHING", (item_id, source, now_utc()))
        return bool(cur)

    async def source_started(self, source: str) -> None:
        await self.db.execute("INSERT INTO source_health(source,last_started_at,consecutive_failures) VALUES(?,?,0) ON CONFLICT(source) DO UPDATE SET last_started_at=excluded.last_started_at", (source, now_utc()))

    async def source_succeeded(self, source: str) -> None:
        await self.db.execute("INSERT INTO source_health(source,last_success_at,consecutive_failures,last_error) VALUES(?,?,0,NULL) ON CONFLICT(source) DO UPDATE SET last_success_at=excluded.last_success_at,consecutive_failures=0,last_error=NULL", (source, now_utc()))

    async def source_failed(self, source: str, error: str) -> None:
        safe_error = str(error).replace("\n", " ")[:300]
        await self.db.execute("INSERT INTO source_health(source,last_started_at,consecutive_failures,last_error) VALUES(?,?,1,?) ON CONFLICT(source) DO UPDATE SET consecutive_failures=consecutive_failures+1,last_error=excluded.last_error", (source, now_utc(), safe_error))

    async def source_health(self) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM source_health ORDER BY source")

    async def notification_health(self, since: int | None = None) -> dict[str, int]:
        """Summarize delivery outcomes without exposing message contents."""
        cutoff = int(since if since is not None else now_utc() - 86400)
        rows = await self.db.fetchall(
            "SELECT result, COUNT(*) AS total FROM notification_history WHERE sent_at>=? GROUP BY result",
            (cutoff,),
        )
        summary = {"sent": 0, "failed": 0, "pending": 0, "other": 0}
        for row in rows:
            key = str(row.get("result") or "other")
            summary[key if key in summary else "other"] += int(row.get("total") or 0)
        return summary

    async def create_news_event(self, tracked: dict[str, Any], item: Any, update_type: str | None = None) -> bool:
        text = f"{item.title} — {item.summary}"[:1000]
        key = hashlib.sha256(f"news|{tracked['provider']}|{tracked['external_id']}|{item.item_id}".encode()).hexdigest()
        status = "officially_confirmed" if item.official else "unverified"
        chosen_type = update_type or ("official_announcement" if item.official else "news_report")
        event = ReleaseItem(key, str(tracked["title"]), str(tracked["format"]), chosen_type,
                            None, item.published_at, status, item.source, item.url, text, item.official)
        return await self.add_release(event, str(tracked["provider"]), str(tracked["external_id"]))
