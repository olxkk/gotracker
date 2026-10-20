"""Environment-based configuration. Secrets are never printed."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    discord_token: str = os.getenv("DISCORD_TOKEN", "")
    mal_client_id: str = os.getenv("MAL_CLIENT_ID", "")
    database_path: str = os.getenv("DATABASE_PATH", str(ROOT_DIR / "data" / "tracker.sqlite3"))
    poll_interval_seconds: int = _int_env("POLL_INTERVAL_SECONDS", 1800, 60)
    request_timeout_seconds: int = _int_env("REQUEST_TIMEOUT_SECONDS", 15, 3)
    max_response_bytes: int = _int_env("MAX_RESPONSE_BYTES", 2_000_000, 4096)
    dev_guild_id: int = _int_env("DEV_GUILD_ID", 0, 0)
    rss_feeds_raw: str = os.getenv("RSS_FEEDS", "Crunchyroll News|https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss|third-party")
    user_agent: str = os.getenv("BOT_USER_AGENT", "AnimeMangaTracker/1.0 (Discord community bot)")

    @property
    def rss_feeds(self) -> list[tuple[str, str, bool]]:
        """Parse `Name|https://feed.url|official;Other|https://...|third-party`."""
        feeds: list[tuple[str, str, bool]] = []
        for item in self.rss_feeds_raw.split(";"):
            item = item.strip()
            if not item:
                continue
            parts = [part.strip() for part in item.split("|", 2)]
            if len(parts) < 2 or not parts[0] or not parts[1].startswith(("https://", "http://")):
                continue
            official = len(parts) == 3 and parts[2].lower() in {"official", "true", "yes"}
            feeds.append((parts[0][:80], parts[1][:500], official))
        return feeds


settings = Settings()
