from __future__ import annotations

import logging
import time

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from bot.database.session import Database
from bot.database.repositories import Repository
from bot.providers.anilist import AniListProvider
from bot.providers.kitsu import KitsuProvider
from bot.providers.myanimelist import MyAnimeListProvider
from bot.providers.mangadex import MangaDexProvider
from bot.providers.official_sources import OfficialSourcesProvider
from bot.services.release_service import ProviderRegistry, ReleaseService
from bot.services.news_service import NewsService
from bot.services.notification_service import NotificationService
from bot.services.scheduler import Scheduler
from bot.utils.logging import configure_logging

log = logging.getLogger(__name__)


class AnimeTrackerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents, allowed_mentions=discord.AllowedMentions.none())
        # Application-command errors are handled by CommandTree, not a generic event name.
        self.tree.on_error = self.on_app_command_error
        self.settings = settings
        self.started_at = int(time.time())
        self.db: Database | None = None
        self.repo: Repository | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self.providers: ProviderRegistry | None = None
        self.rss_provider: OfficialSourcesProvider | None = None
        self.release_service: ReleaseService | None = None
        self.news_service: NewsService | None = None
        self.notification_service: NotificationService | None = None
        self.scheduler: Scheduler | None = None

    async def setup_hook(self) -> None:
        if not self.settings.discord_token:
            raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env and configure it before starting the bot.")
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=12, ttl_dns_cache=300)
        self.http_session = aiohttp.ClientSession(timeout=timeout, connector=connector,
                                                  headers={"User-Agent": self.settings.user_agent})
        self.db = Database(self.settings.database_path)
        await self.db.connect()
        self.repo = Repository(self.db)

        anilist = AniListProvider(self.http_session, self.settings.request_timeout_seconds, self.settings.max_response_bytes)
        kitsu = KitsuProvider(self.http_session, self.settings.request_timeout_seconds, self.settings.max_response_bytes)
        mal = MyAnimeListProvider(self.settings.mal_client_id, self.http_session, self.settings.request_timeout_seconds, self.settings.max_response_bytes)
        mangadex = MangaDexProvider(self.http_session, self.settings.request_timeout_seconds, self.settings.max_response_bytes)
        self.providers = ProviderRegistry(anilist, kitsu, mal, mangadex)
        self.rss_provider = OfficialSourcesProvider(self.settings.rss_feeds, self.http_session,
                                                    self.settings.request_timeout_seconds, min(self.settings.max_response_bytes, 1_000_000),
                                                    self.settings.user_agent)
        self.release_service = ReleaseService(self.repo, self.providers)
        self.news_service = NewsService(self.repo, self.rss_provider)
        self.notification_service = NotificationService(self.repo, self)
        self.scheduler = Scheduler(self.repo, self.providers, self.release_service, self.news_service,
                                   self.notification_service, self.settings.poll_interval_seconds)

        for extension in (
            "bot.commands.tracking",
            "bot.commands.releases",
            "bot.commands.news",
            "bot.commands.notifications",
            "bot.commands.general",
        ):
            await self.load_extension(extension)

        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to the configured development guild", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global slash commands; Discord may take a little time to display global commands", len(synced))

    async def on_ready(self) -> None:
        if self.scheduler:
            self.scheduler.start()  # idempotent across reconnects
        log.info("Bot is ready; logged in as %s", self.user)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need the required server permissions to use this command."
        elif isinstance(error, app_commands.CheckFailure):
            message = "You are not allowed to use this command here."
        else:
            log.error("Slash command failed: %s", error, exc_info=(type(error), error, error.__traceback__))
            message = "The command failed unexpectedly. Your saved watchlist was not intentionally changed; try again later."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def close(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        if self.db:
            await self.db.close()
        await super().close()


def main() -> None:
    configure_logging()
    if not settings.discord_token:
        raise SystemExit("DISCORD_TOKEN is required. Configure it in .env (never paste your token into chat).")
    bot = AnimeTrackerBot()
    try:
        bot.run(settings.discord_token, log_handler=None)
    except KeyboardInterrupt:
        log.info("Shutdown requested")


if __name__ == "__main__":
    main()
