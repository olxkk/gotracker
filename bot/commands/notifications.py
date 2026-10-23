from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands

from .helpers import guild_id, no_guild_message, autocomplete_tracked_titles, resolve_track_argument, track_ambiguous_message



class NotificationsCog(commands.Cog):
    notify = app_commands.Group(name="notify", description="Configure per-server and per-title notifications")

    def __init__(self, bot):
        self.bot = bot


    @notify.command(name="show", description="Recommended: choose a title notification channel and optional role ping")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def show(self, interaction: discord.Interaction, title: str, channel: discord.TextChannel,
                   role: discord.Role | None = None):
        """Simple per-title setup; omitting role intentionally means no ping."""
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if channel.guild.id != gid or (role is not None and role.guild.id != gid):
            await interaction.response.send_message("Choose a channel and role from this server.", ephemeral=True)
            return
        if role is not None and (role.is_default() or role.managed):
            await interaction.response.send_message("Choose a normal server role, not @everyone or a managed integration role.", ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        category = "chapters" if track.get("format") == "MANGA" else "episodes"
        try:
            await self.bot.repo.set_notification_route(
                gid, category, channel.id, provider=track["provider"], external_id=str(track["external_id"]),
                target_mode="role" if role else "none", role_id=role.id if role else None,
                user_id=None, everyone_enabled=False,
            )
        except Exception:
            # Keep user-facing failures clear while logging the underlying error.
            import logging
            logging.getLogger(__name__).exception("Could not save title notification route")
            await interaction.response.send_message("I couldn't save that notification setup. Check the bot logs and try again.", ephemeral=True)
            return
        ping_text = f" and ping {role.mention}" if role else " with no ping"
        await interaction.response.send_message(
            f"Notifications for **{track['title']}** will use {channel.mention}{ping_text}. "
            f"Use `/notify test-title` to test this title's route.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @show.autocomplete("title")
    async def show_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @notify.command(name="test-title", description="Send a real test through a title's configured episode/chapter route")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test_title(self, interaction: discord.Interaction, title: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success, message = await self.bot.notification_service.preview_title(gid, track, interaction.guild)
        await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @test_title.autocomplete("title")
    async def test_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @notify.command(name="routes", description="View saved default routes and title-specific overrides")
    async def routes(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        rows = await self.bot.repo.list_notification_routes(gid)
        embed = discord.Embed(title="Notification routes", color=discord.Color.blurple())
        if not rows:
            embed.description = "No saved routes yet. Use `/notify show` to choose a channel and optional role for a tracked title."
        else:
            for row in rows[:25]:
                scope = f"Title: {row.get('title')}" if row.get("scope") == "title" else "Category default"
                channel = f"<#{row['channel_id']}>"
                target = row.get("target_mode", "none")
                if target == "role" and row.get("role_id"):
                    target = f"role <@&{row['role_id']}>"
                elif target == "user" and row.get("user_id"):
                    target = f"user <@{row['user_id']}>"
                elif target == "everyone":
                    target = "@everyone" if row.get("everyone_enabled") else "everyone (disabled)"
                else:
                    target = "no ping"
                embed.add_field(name=f"{scope} · {row['category']}", value=f"Channel: {channel}\nTarget: {target}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


    @notify.command(name="settings", description="View this server's notification defaults and quiet hours")
    async def settings_view(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        row = await self.bot.repo.ensure_guild(gid)
        channel = f"<#{row['notification_channel_id']}>" if row.get("notification_channel_id") else "Not configured"
        target = row.get("default_target") or "none"
        details = {"none": "No mention", "role": f"Role ID: {row.get('target_role_id') or 'not selected'}",
                   "user": f"User ID: {row.get('target_user_id') or 'not selected'}",
                   "everyone": f"@everyone enabled: {'yes' if row.get('everyone_enabled') else 'no'}"}
        quiet = "Off" if not row.get("quiet_start") or not row.get("quiet_end") else f"{row['quiet_start']}–{row['quiet_end']} ({row.get('timezone') or 'UTC'})"
        embed = discord.Embed(title="Notification settings", color=discord.Color.blurple())
        embed.add_field(name="Notification channel", value=channel, inline=False)
        embed.add_field(name="Default target", value=f"{target} — {details.get(target, 'No mention')}", inline=False)
        embed.add_field(name="Quiet hours", value=quiet, inline=False)
        embed.add_field(name="Everyone safety", value="Enabled" if row.get("everyone_enabled") else "Disabled", inline=True)
        embed.set_footer(text="Settings are isolated to this server. Server configuration requires Manage Server permission.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @notify.command(name="title", description="Turn all notifications for one tracked title on or off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def title(self, interaction: discord.Interaction, title: str, enabled: bool):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        await self.bot.repo.update_track_setting(gid, track["provider"], str(track["external_id"]), "notifications_enabled", enabled)
        await interaction.response.send_message(f"Notifications for **{track['title']}** are now {'on' if enabled else 'off'} in this server.", ephemeral=True)

    @title.autocomplete("title")
    async def title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @notify.command(name="types", description="View or change episode, chapter, schedule, delay, hiatus, and news alerts")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def types(self, interaction: discord.Interaction, title: str, episodes: bool | None = None, chapters: bool | None = None,
                    schedule_changes: bool | None = None, delays: bool | None = None, hiatus: bool | None = None, announcements: bool | None = None):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        values = {"notify_episodes": episodes, "notify_chapters": chapters, "notify_schedule": schedule_changes,
                  "notify_delays": delays, "notify_hiatus": hiatus, "notify_announcements": announcements}
        changes = []
        for field, value in values.items():
            if value is not None:
                await self.bot.repo.update_track_setting(gid, track["provider"], str(track["external_id"]), field, value)
                changes.append(f"{field.removeprefix('notify_').replace('_', ' ')}: {'on' if value else 'off'}")
        if not changes:
            changes = [f"{field.removeprefix('notify_').replace('_', ' ')}: {'on' if track.get(field, 1) else 'off'}" for field in values]
            message = "Current preferences — " + "; ".join(changes)
        else:
            message = "Updated preferences — " + "; ".join(changes)
        await interaction.response.send_message(f"**{track['title']}**\n{message}", ephemeral=True)

    @types.autocomplete("title")
    async def types_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    @notify.command(name="quiet-hours", description="Set quiet hours using 24-hour times and an IANA timezone; OFF/OFF disables")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def quiet_hours(self, interaction: discord.Interaction, start: str, end: str, timezone: str = "UTC"):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        start, end = start.strip().upper(), end.strip().upper()
        if start == "OFF" and end == "OFF":
            await self.bot.repo.set_guild_setting(gid, "quiet_start", None)
            await self.bot.repo.set_guild_setting(gid, "quiet_end", None)
            await interaction.response.send_message("Quiet hours disabled.", ephemeral=True)
            return
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end):
            await interaction.response.send_message("Use times like `22:00` and `07:00`, or enter `OFF` for both start and end.", ephemeral=True)
            return
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            await interaction.response.send_message("Unknown timezone. Use an IANA name such as `Europe/Athens` or `UTC`.", ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "quiet_start", start)
        await self.bot.repo.set_guild_setting(gid, "quiet_end", end)
        await self.bot.repo.set_guild_setting(gid, "timezone", timezone)
        await interaction.response.send_message(f"Quiet hours set to **{start}–{end}** in **{timezone}**. Ordinary alerts will be held until quiet hours end; official announcements, delays, and hiatus notices can still be sent.", ephemeral=True)

    @notify.command(name="guide", description="Show the recommended notification setup steps")
    async def guide(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Notifications: quick setup", color=discord.Color.blurple())
        embed.description = (
            "**1. Add the show first:** use `/track add` and choose the exact anime or manga.\n\n"
            "**2. Choose where its updates go:** run `/notify show`, select the tracked title and a channel, "
            "then optionally choose a role to ping. Leave the role empty for no ping.\n\n"
            "**3. Test it:** run `/notify test-title` and choose the same title. This sends a real test message "
            "to its configured channel; if you chose a role, that role may be pinged.\n\n"
            "Use `/notify routes` to check saved destinations, `/notify settings` to view server defaults, "
            "`/notify title` to pause or resume a title, and `/notify types` to control episode/chapter alerts. "
            "`/notify quiet-hours` is optional. Old saved routes continue to work, but the advanced setup commands have been removed."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

async def setup(bot):
    await bot.add_cog(NotificationsCog(bot))
