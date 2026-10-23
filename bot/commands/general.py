from __future__ import annotations

import time
import logging
import discord
from discord import app_commands
from discord.ext import commands

from .helpers import guild_id, no_guild_message

log = logging.getLogger(__name__)


class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show the bot's slash commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Anime & Manga Tracker — command guide",
            description=(
                "Use slash commands (`/`). Title fields usually support autocomplete. "
                "Search results are not added until you select a result. Most setup commands are server-admin only. "
                "For the simplest notification setup, start with `/notify guide`."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Tracking — `/track`",
            value=("`add` search and select a title · `remove` stop tracking a title · `list` view this server's list · "
                   "`search` search without adding · `info` view title details"), inline=False)
        embed.add_field(
            name="Release information — `/release`",
            value=("`next` next known schedule · `latest` latest recorded release · `check` refresh a tracked title now · "
                   "`upcoming` server schedule · `history` recorded changes for a title"), inline=False)
        embed.add_field(
            name="News — `/news`",
            value="`title` search configured news feeds · `upcoming` combine tracked schedules and relevant announcements", inline=False)
        embed.add_field(
            name="Notifications — `/notify`",
            value=("`guide`, `show`, `test-title`, `routes`, `settings`, `title`, `types`, `quiet-hours`. "
                   "Start with `guide`, use `show` to set a title's channel and optional role, then `test-title` to check it. "
                   "The test sends a real message and may ping the configured role."), inline=False)
        embed.add_field(
            name="General",
            value="`/random` choose an anime by status, score, genre, episode count or year · `/status` bot, database, notification and provider health · `/settings` effective settings · `/help` this guide", inline=False)
        embed.set_footer(text="Scheduled airing times do not prove streaming availability. Manga chapter release dates are only reported when reliable data exists.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="random", description="Pick an anime to watch, with optional filters")
    @app_commands.describe(
        category="What kind of anime should I pick?",
        minimum_score="Minimum AniList score out of 100 (used for Highly rated)",
        genre="Optional genre filter",
        max_episodes="Only suggest anime with this many episodes or fewer",
        year="Only suggest anime that started in this year",
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="Currently releasing", value="RELEASING"),
        app_commands.Choice(name="Fully released", value="FINISHED"),
        app_commands.Choice(name="Highly rated", value="HIGH_RATED"),
    ], genre=[
        app_commands.Choice(name=name, value=name) for name in [
            "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror", "Mahou Shoujo",
            "Mecha", "Music", "Mystery", "Psychological", "Romance", "Sci-Fi", "Slice of Life",
            "Sports", "Supernatural", "Thriller"
        ]
    ])
    async def random_anime(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        minimum_score: app_commands.Range[int, 1, 100] = 75,
        genre: app_commands.Choice[str] | None = None,
        max_episodes: app_commands.Range[int, 1, 100] | None = None,
        year: app_commands.Range[int, 1970, 2100] | None = None,
    ):
        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            result = await self.bot.providers.providers["anilist"].random_anime(
                category.value, int(minimum_score), genre.value if genre else None,
                int(max_episodes) if max_episodes is not None else None,
                int(year) if year is not None else None,
            )
        except Exception as exc:
            log.warning("Random anime lookup failed (%s): %s", type(exc).__name__, str(exc)[:200])
            await interaction.followup.send(
                "AniList couldn't find a pick just now. Give it a moment and try again.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if not result:
            filters = []
            if genre:
                filters.append(f"genre **{genre.name}**")
            if max_episodes is not None:
                filters.append(f"**{max_episodes} episodes or fewer**")
            if year is not None:
                filters.append(f"year **{year}**")
            if category.value == "HIGH_RATED":
                filters.append(f"score **{minimum_score}/100 or higher**")
            detail = (" with " + ", ".join(filters)) if filters else ""
            await interaction.followup.send(
                f"I couldn't find an anime for **{category.name}**{detail}. Try removing a filter or lowering the score.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        media, score = result
        # Random lookup deliberately uses compact fields. Fetch the selected title's full
        # details separately so a long page of descriptions cannot exceed the response cap.
        if not media.description:
            try:
                detailed = await self.bot.providers.providers["anilist"].get(media.external_id, "ANIME")
                if detailed is not None:
                    media = detailed
            except Exception as exc:
                log.debug("Could not load synopsis for random pick (%s)", type(exc).__name__)
        embed = discord.Embed(title=media.title[:250], url=media.url, description=(media.description or "No synopsis is available.")[:3500], color=discord.Color.blurple())
        if media.cover_url.startswith(("https://", "http://")):
            embed.set_thumbnail(url=media.cover_url)
        embed.add_field(name="Pick", value=category.name, inline=True)
        embed.add_field(name="AniList score", value=f"{score}/100" if score else "Not available", inline=True)
        embed.add_field(name="Status", value=media.status.replace("_", " ").title(), inline=True)
        embed.add_field(name="Episodes", value=str(media.episodes) if media.episodes is not None else "Unknown", inline=True)
        active_filters = [genre.name if genre else None, f"≤{max_episodes} eps" if max_episodes is not None else None, str(year) if year is not None else None]
        active_filters = [item for item in active_filters if item]
        if active_filters:
            embed.add_field(name="Filters", value=" · ".join(active_filters), inline=False)
        if media.next_episode and media.next_airing_at:
            embed.add_field(name="Next airing", value=f"Episode {media.next_episode} · <t:{int(media.next_airing_at)}:F>", inline=False)
        embed.set_footer(text="Picked from AniList · Run /random again for another idea")
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="status", description="Check whether the bot, database, and data sources are healthy")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tracks = (await self.bot.repo.list_tracks(int(interaction.guild_id))
                  if interaction.guild_id else await self.bot.repo.all_tracked_titles())
        health = await self.bot.repo.source_health()
        started = int(getattr(self.bot, "started_at", time.time()))
        uptime = max(0, int(time.time()) - started)
        days, rem = divmod(uptime, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        latency_ms = round(float(getattr(self.bot, "latency", 0.0)) * 1000)
        db_state = "OK"
        try:
            await self.bot.db.fetchone("SELECT 1 AS ok")
        except Exception:
            db_state = "not responding"
            log.exception("Database health check failed")
        scheduler = getattr(self.bot, "scheduler", None)
        cycle = getattr(scheduler, "last_cycle", None) if scheduler else None
        last_cycle_at = getattr(scheduler, "last_cycle_at", None) if scheduler else None
        embed = discord.Embed(title="Bot status", color=discord.Color.green() if db_state == "OK" else discord.Color.red())
        embed.add_field(name="Uptime", value=f"{days}d {hours}h {minutes}m", inline=True)
        embed.add_field(name="Discord latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Database", value=db_state, inline=True)
        embed.add_field(name="Tracked title entries", value=str(len(tracks)), inline=True)
        embed.add_field(name="Polling interval", value=f"{self.bot.settings.poll_interval_seconds // 60} minutes", inline=True)
        if last_cycle_at:
            embed.add_field(name="Last monitoring run", value=f"<t:{int(last_cycle_at)}:R>", inline=True)
        if cycle:
            embed.add_field(name="Last run results", value=f"Checked: {cycle.get('checked', 0)} · Errors: {cycle.get('errors', 0)} · Notifications sent: {cycle.get('notifications', 0)}", inline=False)
        try:
            notify_health = await self.bot.repo.notification_health()
            embed.add_field(
                name="Notifications (last 24h)",
                value=f"Sent: {notify_health['sent']} · Failed: {notify_health['failed']} · Pending: {notify_health['pending']}",
                inline=False,
            )
        except Exception:
            log.exception("Notification health check failed")
            embed.add_field(name="Notifications", value="Couldn't read notification history right now.", inline=False)
        if health:
            lines = []
            for row in health[:10]:
                stamp = f"<t:{int(row['last_success_at'])}:R>" if row.get("last_success_at") else "never"
                failures = int(row.get("consecutive_failures") or 0)
                state = "healthy" if failures == 0 else f"⚠️ {failures} consecutive failure(s)"
                lines.append(f"**{row['source']}**: {state}; last success {stamp}")
            embed.add_field(name="Data sources", value="\n".join(lines)[:1024], inline=False)
        else:
            embed.add_field(name="Data sources", value="No source checks have completed yet.", inline=False)
        embed.set_footer(text="If a source is failing, try /release check for a title and check the hosting logs for details.")
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="settings", description="Show effective bot and this server's settings")
    async def settings(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Tracker settings", color=discord.Color.blurple())
        embed.add_field(name="Provider availability", value=f"AniList: enabled\nKitsu: enabled\nMyAnimeList: {'enabled' if self.bot.settings.mal_client_id else 'disabled (optional client ID not configured)'}\nMangaDex: enabled for manga\nRSS feeds: {len(self.bot.rss_provider.feeds)} configured", inline=False)
        embed.add_field(name="Monitoring", value=f"Poll interval: {self.bot.settings.poll_interval_seconds} seconds\nHTTP timeout: {self.bot.settings.request_timeout_seconds} seconds\nDatabase: persistent SQLite file", inline=False)
        if interaction.guild_id:
            row = await self.bot.repo.ensure_guild(int(interaction.guild_id))
            channel = f"<#{row['notification_channel_id']}>" if row.get("notification_channel_id") else "not configured"
            embed.add_field(name="This server", value=f"Notification channel: {channel}\nTarget: {row.get('default_target','none')}\n@everyone: {'enabled' if row.get('everyone_enabled') else 'disabled'}", inline=False)
        embed.set_footer(text="Commands that change server settings require Manage Server; enabling @everyone requires Administrator and exact confirmation.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
