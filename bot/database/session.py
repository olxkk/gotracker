from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id INTEGER PRIMARY KEY,
  notification_channel_id INTEGER,
  default_target TEXT NOT NULL DEFAULT 'none' CHECK(default_target IN ('none','role','user','everyone')),
  target_role_id INTEGER,
  target_user_id INTEGER,
  everyone_enabled INTEGER NOT NULL DEFAULT 0,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  quiet_start TEXT,
  quiet_end TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
  provider TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL CHECK(format IN ('ANIME','MANGA')),
  url TEXT NOT NULL,
  cover_url TEXT,
  description TEXT,
  status TEXT,
  episodes INTEGER,
  chapters INTEGER,
  next_airing_at INTEGER,
  next_episode INTEGER,
  start_date TEXT,
  end_date TEXT,
  last_checked_at INTEGER,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(provider, external_id)
);
CREATE TABLE IF NOT EXISTS tracked_titles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  provider TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL CHECK(format IN ('ANIME','MANGA')),
  notifications_enabled INTEGER NOT NULL DEFAULT 1,
  notify_episodes INTEGER NOT NULL DEFAULT 1,
  notify_chapters INTEGER NOT NULL DEFAULT 1,
  notify_schedule INTEGER NOT NULL DEFAULT 1,
  notify_delays INTEGER NOT NULL DEFAULT 1,
  notify_hiatus INTEGER NOT NULL DEFAULT 1,
  notify_announcements INTEGER NOT NULL DEFAULT 1,
  added_at INTEGER NOT NULL,
  last_checked_at INTEGER,
  FOREIGN KEY(provider, external_id) REFERENCES media(provider, external_id) ON DELETE CASCADE,
  UNIQUE(guild_id, provider, external_id)
);
CREATE TABLE IF NOT EXISTS release_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  release_key TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL,
  update_type TEXT NOT NULL,
  number INTEGER,
  release_at INTEGER,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT NOT NULL,
  summary TEXT,
  official INTEGER NOT NULL DEFAULT 0,
  detected_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_events_title ON release_events(provider, external_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_release_events_date ON release_events(release_at);
CREATE TABLE IF NOT EXISTS notification_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  release_key TEXT NOT NULL,
  channel_id INTEGER NOT NULL,
  sent_at INTEGER NOT NULL,
  message_id INTEGER,
  result TEXT NOT NULL DEFAULT 'sent',
  UNIQUE(guild_id, release_key)
);
CREATE TABLE IF NOT EXISTS guild_notification_routes (
  guild_id INTEGER NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('episodes','chapters','news','schedule')),
  channel_id INTEGER NOT NULL,
  target_mode TEXT NOT NULL DEFAULT 'none' CHECK(target_mode IN ('none','role','user','everyone')),
  role_id INTEGER,
  user_id INTEGER,
  everyone_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(guild_id, category),
  FOREIGN KEY(guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS title_notification_routes (
  guild_id INTEGER NOT NULL,
  provider TEXT NOT NULL,
  external_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('episodes','chapters','news','schedule')),
  channel_id INTEGER NOT NULL,
  target_mode TEXT NOT NULL DEFAULT 'none' CHECK(target_mode IN ('none','role','user','everyone')),
  role_id INTEGER,
  user_id INTEGER,
  everyone_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(guild_id, provider, external_id, category),
  FOREIGN KEY(guild_id, provider, external_id) REFERENCES tracked_titles(guild_id, provider, external_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS source_health (
  source TEXT PRIMARY KEY,
  last_started_at INTEGER,
  last_success_at INTEGER,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS seen_feed_items (
  item_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  seen_at INTEGER NOT NULL
);
"""


class Database:
    """Small async SQLite wrapper with explicit transactions and persistent file storage."""

    def __init__(self, path: str):
        self.path = str(Path(path).expanduser().resolve())
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._connection is not None:
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected")
        return self._connection

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cursor.rowcount

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    def transaction(self):
        """Use `async with db.transaction() as conn:` for multi-statement atomic writes."""
        return _Transaction(self)


class _Transaction:
    def __init__(self, db: Database):
        self.db = db

    async def __aenter__(self):
        await self.db._lock.acquire()
        await self.db.conn.execute("BEGIN IMMEDIATE")
        return self.db.conn

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                await self.db.conn.rollback()
            else:
                await self.db.conn.commit()
        finally:
            self.db._lock.release()
        return False
