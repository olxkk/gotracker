from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands

from .helpers import guild_id, no_guild_message, autocomplete_tracked_titles, resolve_track_argument, track_ambiguous_message
from ..utils.embeds import clean_text, media_embed, release_embed


class ReleasesCog(commands.Cog):
    release = app_commands.Group(name="release", description="Check upcoming schedules and release history")

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_media(self, interaction: discord.Interaction, title: str):
        track = await resolve_track_argument(interaction, title)
        if track:
            provider, external_id, media_format = track["provider"], str(track["external_id"]), track["format"]
        else:
            # Search both formats, preferring exact AniList matches because it supplies airing schedules.
            results = []
            for fmt in ("ANIME", "MANGA"):
                try:
                    results.extend(await self.bot.providers.search(title, fmt, limit=6))
                except Exception:
                    continue
            exact = [item for item in results if item.title.casefold() == title.casefold()]
            anilist_exact = [item for item in exact if item.provider == "anilist"]
            if len(anilist_exact) == 1:
                media = anilist_exact[0]
            elif len(exact) == 1:
                media = exact[0]
            else:
                return None, None
            provider, external_id, media_format = media.provider, media.external_id, media.format
        try:
            media = await self.bot.providers.get(provider, external_id, media_format)
        except Exception:
            media = None
        return (track, media) if track else (None, media)

    @release.command(name="next", description="Show the next known episode schedule or chapter-data limitations")
    async def next_release(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        track, media = await self._resolve_media(interaction, title)
        if media is None:
            await interaction.followup.send(track_ambiguous_message(), ephemeral=True)
            return
        await self.bot.repo.save_media(media)
        if media.format == "ANIME" and media.next_airing_at:
            stamp = int(media.next_airing_at)
            embed = discord.Embed(title=f"Next scheduled airing: {clean_text(media.title, 200)}", url=media.url, color=discord.Color.blurple())
            embed.add_field(name="Episode", value=str(media.next_episode if media.next_episode is not None else "Unknown"), inline=True)
            embed.add_field(name="Date and time", value=f"<t:{stamp}:F>\n<t:{stamp}:R> (Discord local timezone)", inline=False)
            embed.add_field(name="Status", value="Scheduled by AniList; not proof that the episode is available to stream.", inline=False)
            embed.add_field(name="Source", value=f"[AniList entry]({media.url})", inline=False)
            if media.cover_url.startswith("https://"):
                embed.set_thumbnail(url=media.cover_url)
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif media.format == "MANGA":
            embed = discord.Embed(title=f"Next chapter: {clean_text(media.title, 200)}", url=media.url, color=discord.Color.light_grey())
            embed.description = "No reliable upcoming chapter number or release time is available from this metadata source. The catalogue chapter count is not treated as proof of a new chapter."
            embed.add_field(name="Known catalogue count", value=str(media.chapters) if media.chapters is not None else "Unknown", inline=True)
            embed.add_field(name="Confirmation status", value="No reliable release information", inline=True)
            embed.add_field(name="Source", value=f"[Open catalogue entry]({media.url})", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"No reliable upcoming episode schedule is available for **{clean_text(media.title, 150)}**. Source: {media.url}", ephemeral=True)

    @next_release.autocomplete("title")
    async def next_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @release.command(name="latest", description="Show the latest release event recorded by the bot")
    async def latest(self, interaction: discord.Interaction, title: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        events = await self.bot.repo.get_events(track["provider"], str(track["external_id"]), 20)
        now = int(time.time())
        past = [x for x in events if x.get("release_at") and int(x["release_at"]) <= now and x.get("update_type") not in {"upcoming_episode", "schedule_change"}]
        if not past:
            if track["format"] == "MANGA":
                detail = f"Known catalogue chapter count: {track.get('chapters') if track.get('chapters') is not None else 'unknown'}. This is not a latest-release record."
            else:
                detail = f"Known catalogue episode count: {track.get('episodes') if track.get('episodes') is not None else 'unknown'}. No recent release event has been reliably recorded."
            await interaction.response.send_message(f"**{clean_text(track['title'], 150)}**\n{detail}\nSource: {track.get('url') or 'unknown'}", ephemeral=True)
            return
        await interaction.response.send_message(embed=release_embed(past[0]), ephemeral=True)

    @latest.autocomplete("title")
    async def latest_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @release.command(name="check", description="Refresh one tracked title now; this may call the source API")
    async def check(self, interaction: discord.Interaction, title: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            fresh, events = await self.bot.scheduler.refresh_one(track["provider"], str(track["external_id"]), track["format"])
            description = f"Refreshed **{clean_text(fresh.title, 150)}** from {fresh.provider}."
            if events:
                description += f"\nDetected {len(events)} schedule change(s). Notifications are deduplicated per server."
            elif fresh.format == "MANGA":
                description += "\nThis provider does not reliably report new chapter availability; no chapter release was inferred."
            else:
                description += "\nNo new schedule change was detected. A scheduled airing is not proof of streaming availability."
            await interaction.followup.send(description, ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"Refresh failed temporarily ({type(exc).__name__}). The last saved data was kept; try again later.", ephemeral=True)

    @check.autocomplete("title")
    async def check_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @release.command(name="upcoming", description="List upcoming scheduled episodes for this server's tracked anime")
    async def upcoming(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        rows = await self.bot.repo.upcoming_for_guild(gid, limit=15)
        if not rows:
            await interaction.response.send_message("No reliable future airing schedule is currently available for this server's tracked titles. Manga chapter schedules are only shown when a provider supplies reliable dates.", ephemeral=True)
            return
        embed = discord.Embed(title="Upcoming tracked releases", color=discord.Color.blurple())
        for row in rows[:15]:
            embed.add_field(name=clean_text(row["title"], 150), value=f"Episode {row['next_episode'] if row['next_episode'] is not None else 'unknown'} · <t:{int(row['next_airing_at'])}:F>\nScheduled; availability not verified · [Source]({row['url']})", inline=False)
        if len(rows) >= 15:
            embed.set_footer(text="Showing up to 15 upcoming entries. Dates are scheduled, not proof of streaming availability.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @release.command(name="history", description="Show recent recorded releases and schedule changes for a tracked title")
    async def history(self, interaction: discord.Interaction, title: str):
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        events = await self.bot.repo.get_events(track["provider"], str(track["external_id"]), 10)
        if not events:
            await interaction.response.send_message(f"No release or schedule-change history has been recorded for **{clean_text(track['title'], 150)}** yet. This doesn't mean there has been no release.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Release history: {clean_text(track['title'], 200)}", color=discord.Color.blurple())
        for event in events[:10]:
            date = f"<t:{int(event['release_at'])}:F>" if event.get("release_at") else "Date unknown"
            number = f" · #{event['number']}" if event.get("number") is not None else ""
            link = f"\n[Source]({event['url']})" if str(event.get("url", "")).startswith(("https://", "http://")) else ""
            embed.add_field(name=f"{event['update_type'].replace('_', ' ').title()}{number}", value=f"{date} · {event['status'].replace('_',' ').title()}\n{clean_text(event.get('summary') or '', 300)}{link}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @history.autocomplete("title")
    async def history_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)


async def setup(bot):
    await bot.add_cog(ReleasesCog(bot))
