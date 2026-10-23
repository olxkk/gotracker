from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from .helpers import TrackResultView, guild_id, no_guild_message, autocomplete_tracked_titles, resolve_track_argument, track_ambiguous_message
from ..utils.embeds import media_embed, clean_text

log = logging.getLogger(__name__)


class TrackingCog(commands.Cog):
    track = app_commands.Group(name="track", description="Manage this server's anime and manga watchlist")

    def __init__(self, bot):
        self.bot = bot

    @track.command(name="add", description="Add a title: search, then select the exact anime or manga")
    @app_commands.describe(title="Title to search for", media_format="Search anime or manga catalogues", source="Choose a specific catalogue, or leave blank to search all supported sources")
    @app_commands.choices(media_format=[app_commands.Choice(name="Anime", value="ANIME"), app_commands.Choice(name="Manga", value="MANGA")], source=[app_commands.Choice(name="All supported sources", value="all"), app_commands.Choice(name="AniList", value="anilist"), app_commands.Choice(name="Kitsu", value="kitsu"), app_commands.Choice(name="MyAnimeList", value="myanimelist"), app_commands.Choice(name="MangaDex (manga only)", value="mangadex")])
    async def add(self, interaction: discord.Interaction, title: str, media_format: app_commands.Choice[str], source: str = "all"):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.bot.providers.search(title, media_format.value, limit=10, source=None if source == "all" else source)
        except Exception as exc:
            log.warning("Search providers unavailable: %s", type(exc).__name__)
            results = []
        if not results:
            await interaction.followup.send("No results were returned. Check the spelling or try `/track search`; a provider may be temporarily unavailable.", ephemeral=True)
            return
        view = TrackResultView(self, gid, results)
        await interaction.followup.send("Choose the exact catalogue entry. The first result is not automatically added.", view=view, ephemeral=True)

    @track.command(name="remove", description="Stop tracking a title in this server (does not delete it globally)")
    async def remove(self, interaction: discord.Interaction, title: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        tracks = await self.bot.repo.list_tracks(gid)
        query = title.strip()
        if ":" in query:
            provider, external_id = query.split(":", 1)
            match = [x for x in tracks if x["provider"] == provider and str(x["external_id"]) == external_id]
        else:
            match = [x for x in tracks if str(x["title"]).casefold() == query.casefold()]
        if len(match) != 1:
            await interaction.response.send_message("I couldn't find exactly one matching tracked title. Use the autocomplete list to choose the exact entry.", ephemeral=True)
            return
        removed = await self.bot.repo.remove_track(gid, str(match[0]["id"]))
        await interaction.response.send_message(f"Removed **{clean_text(match[0]['title'], 150)}** from this server." if removed else "That title was already removed.", ephemeral=True)

    @remove.autocomplete("title")
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @track.command(name="list", description="View this server's tracked anime and manga")
    async def list_titles(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        rows = await self.bot.repo.list_tracks(gid)
        if not rows:
            await interaction.response.send_message("This server isn't tracking any titles yet. Use `/track add` to start.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Tracked titles ({len(rows)})", color=discord.Color.blurple())
        # Keep the combined embed well below Discord's 6000-character aggregate limit.
        for row in rows[:10]:
            label = "Anime" if row["format"] == "ANIME" else "Manga"
            detail = f"**{label}** · {row['provider']} · notifications {'on' if row['notifications_enabled'] else 'off'}"
            if row["format"] == "ANIME":
                if row.get("next_episode") and row.get("next_airing_at"):
                    detail += f"\nNext: episode {row['next_episode']} · <t:{int(row['next_airing_at'])}:F> (scheduled)"
                else:
                    detail += "\nUpcoming episode: no reliable schedule"
            else:
                detail += f"\nLatest tracked chapter: {row.get('chapters') if row.get('chapters') is not None else 'unknown'} · chapter notifications use MangaDex when selected" if row.get("provider") == "mangadex" else f"\nCatalogue chapter count: {row.get('chapters') if row.get('chapters') is not None else 'unknown'} · latest release: unknown"
            url = row.get("url")
            if url and str(url).startswith(("https://", "http://")):
                detail += f"\n[Source]({url})"
            embed.add_field(name=clean_text(row["title"], 250), value=detail[:1000], inline=False)
        if len(rows) > 10:
            embed.set_footer(text=f"Showing first 10 of {len(rows)} tracked titles to keep the embed readable. Use autocomplete on a title command to find a specific entry.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @track.command(name="search", description="Search catalogues without adding a result to the watchlist")
    @app_commands.describe(source="Choose a specific catalogue, or leave blank to search all supported sources")
    @app_commands.choices(media_format=[app_commands.Choice(name="Anime", value="ANIME"), app_commands.Choice(name="Manga", value="MANGA")], source=[app_commands.Choice(name="All supported sources", value="all"), app_commands.Choice(name="AniList", value="anilist"), app_commands.Choice(name="Kitsu", value="kitsu"), app_commands.Choice(name="MyAnimeList", value="myanimelist"), app_commands.Choice(name="MangaDex (manga only)", value="mangadex")])
    async def search(self, interaction: discord.Interaction, title: str, media_format: app_commands.Choice[str], source: str = "all"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.bot.providers.search(title, media_format.value, limit=10, source=None if source == "all" else source)
        except Exception as exc:
            log.warning("Title search failed: %s", type(exc).__name__)
            results = []
        if not results:
            await interaction.followup.send("No matching titles found, or all providers are temporarily unavailable.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Search results for {clean_text(title, 100)}", color=discord.Color.blurple())
        for item in results[:10]:
            embed.add_field(name=f"{clean_text(item.title, 200)} · {item.provider}", value=f"{item.format.title()} · {item.status}\n[Open source]({item.url})", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @track.command(name="info", description="View catalogue details for a title tracked by this server")
    async def info(self, interaction: discord.Interaction, title: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        track = await resolve_track_argument(interaction, title)
        if track is None:
            results = []
            for fmt in ("ANIME", "MANGA"):
                try:
                    results.extend(await self.bot.providers.search(title, fmt, limit=6))
                except Exception:
                    continue
            exact = [x for x in results if x.title.casefold() == title.casefold()]
            anilist_exact = [x for x in exact if x.provider == "anilist"]
            if len(anilist_exact) == 1:
                fresh = anilist_exact[0]
            elif len(exact) == 1:
                fresh = exact[0]
            else:
                await interaction.followup.send(track_ambiguous_message(), ephemeral=True)
                return
        else:
            try:
                fresh = await self.bot.providers.get(track["provider"], str(track["external_id"]), track["format"])
            except Exception:
                fresh = None
            if fresh is None:
                fresh = track
            else:
                await self.bot.repo.save_media(fresh)
        await interaction.followup.send(embed=media_embed(fresh.to_dict() if hasattr(fresh, "to_dict") else fresh, getattr(fresh, "provider", "catalogue")), ephemeral=True)

    @info.autocomplete("title")
    async def info_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)


async def setup(bot):
    await bot.add_cog(TrackingCog(bot))
