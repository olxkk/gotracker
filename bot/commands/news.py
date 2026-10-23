from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .helpers import guild_id, no_guild_message, autocomplete_tracked_titles, resolve_track_argument, track_ambiguous_message
from ..utils.embeds import clean_text, news_embed


class NewsCog(commands.Cog):
    news = app_commands.Group(name="news", description="Search official announcements and configured RSS news sources")

    def __init__(self, bot):
        self.bot = bot

    @news.command(name="title", description="Find recent news for an anime or manga title")
    async def title_news(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.bot.news_service.search(title, limit=10)
        except Exception as exc:
            await interaction.followup.send(f"News sources are temporarily unavailable ({type(exc).__name__}).", ephemeral=True)
            return
        if not results:
            if not self.bot.rss_provider.feeds:
                await interaction.followup.send("No RSS news sources are configured yet. Add permitted feed URLs to `RSS_FEEDS` in `.env` and restart the bot. No news has been inferred.", ephemeral=True)
            else:
                await interaction.followup.send(f"No matching recent news was found for **{clean_text(title, 150)}** in the configured feeds. This is not proof that no announcement exists.", ephemeral=True)
            return
        for item in results[:10]:
            await interaction.followup.send(embed=news_embed(item), ephemeral=True)

    @title_news.autocomplete("title")
    async def title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @news.command(name="upcoming", description="Show upcoming tracked anime schedules and relevant recent announcements")
    async def upcoming_news(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        tracks = await self.bot.repo.list_tracks(gid)
        output_count = 0
        schedules = await self.bot.repo.upcoming_for_guild(gid, limit=15)
        if schedules:
            embed = discord.Embed(title="Upcoming scheduled anime episodes", color=discord.Color.blurple())
            for row in schedules[:15]:
                embed.add_field(name=clean_text(row["title"], 180), value=f"Episode {row['next_episode'] if row['next_episode'] is not None else 'unknown'} · <t:{int(row['next_airing_at'])}:F>\nScheduled; availability not verified · [Source]({row['url']})", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            output_count += 1
        try:
            news_items = await self.bot.news_service.upcoming_announcements(tracks, limit=8)
        except Exception:
            news_items = []
        for item in news_items[:8]:
            await interaction.followup.send(embed=news_embed(item), ephemeral=True)
            output_count += 1
        if not output_count:
            note = "No matching upcoming schedule or relevant announcement was found."
            if not self.bot.rss_provider.feeds:
                note += " RSS feeds are not configured, and chapter release dates are not guessed."
            await interaction.followup.send(note, ephemeral=True)


async def setup(bot):
    await bot.add_cog(NewsCog(bot))
