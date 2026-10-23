from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands

from .helpers import guild_id, no_guild_message, autocomplete_tracked_titles, resolve_track_argument, track_ambiguous_message

TARGET_CHOICES = [
    app_commands.Choice(name="None — no ping", value="none"),
    app_commands.Choice(name="Role", value="role"),
    app_commands.Choice(name="User", value="user"),
    app_commands.Choice(name="Everyone (must be explicitly enabled)", value="everyone"),
]


class NotificationsCog(commands.Cog):
    notify = app_commands.Group(name="notify", description="Configure per-server and per-title notifications")

    def __init__(self, bot):
        self.bot = bot

    ROUTE_CATEGORIES = [
        app_commands.Choice(name="Anime episodes", value="episodes"),
        app_commands.Choice(name="Manga chapters", value="chapters"),
        app_commands.Choice(name="News and announcements", value="news"),
        app_commands.Choice(name="Schedules and delays", value="schedule"),
    ]

    @notify.command(name="route", description="Advanced: set the default channel and ping for one update category")
    @app_commands.choices(category=ROUTE_CATEGORIES, target=TARGET_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def route(self, interaction: discord.Interaction, category: app_commands.Choice[str],
                    channel: discord.TextChannel, target: app_commands.Choice[str],
                    role: discord.Role | None = None, member: discord.Member | None = None,
                    confirmation: str = ""):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if channel.guild.id != gid or (role is not None and role.guild.id != gid) or (member is not None and member.guild.id != gid):
            await interaction.response.send_message("Choose the channel, role, and member from this server.", ephemeral=True)
            return
        ok, message, route_kwargs = self._validate_route_target(interaction, target.value, role, member, confirmation)
        if not ok:
            await interaction.response.send_message(message, ephemeral=True)
            return
        await self.bot.repo.set_notification_route(gid, category.value, channel.id, **route_kwargs)
        await interaction.response.send_message(
            f"Default route for **{category.name}** set to {channel.mention}. Ping target: **{target.name}**. "
            "Title-specific routes can override this default.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @notify.command(name="title-route", description="Advanced: set a channel and ping override for one title and update type")
    @app_commands.choices(category=ROUTE_CATEGORIES, target=TARGET_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def title_route(self, interaction: discord.Interaction, title: str,
                          category: app_commands.Choice[str], channel: discord.TextChannel,
                          target: app_commands.Choice[str], role: discord.Role | None = None,
                          member: discord.Member | None = None, confirmation: str = ""):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if channel.guild.id != gid or (role is not None and role.guild.id != gid) or (member is not None and member.guild.id != gid):
            await interaction.response.send_message("Choose the channel, role, and member from this server.", ephemeral=True)
            return
        track = await resolve_track_argument(interaction, title)
        if not track:
            await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
            return
        ok, message, route_kwargs = self._validate_route_target(interaction, target.value, role, member, confirmation)
        if not ok:
            await interaction.response.send_message(message, ephemeral=True)
            return
        await self.bot.repo.set_notification_route(gid, category.value, channel.id,
            provider=track["provider"], external_id=str(track["external_id"]), **route_kwargs)
        await interaction.response.send_message(
            f"Title override for **{track['title']}** / **{category.name}** set to {channel.mention}. "
            f"Ping target: **{target.name}**. This overrides the category default for this title and category.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @title_route.autocomplete("title")
    async def title_route_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

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
            embed.description = "No category routes configured yet. Set one with `/notify route`."
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

    @notify.command(name="route-clear", description="Advanced: clear a category default or one title-specific route")
    @app_commands.choices(category=ROUTE_CATEGORIES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def route_clear(self, interaction: discord.Interaction, category: app_commands.Choice[str], title: str | None = None):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if title:
            track = await resolve_track_argument(interaction, title)
            if not track:
                await interaction.response.send_message(track_ambiguous_message(), ephemeral=True)
                return
            removed = await self.bot.repo.delete_notification_route(gid, category.value, provider=track["provider"], external_id=str(track["external_id"]))
            scope = f"the **{track['title']}** override"
        else:
            removed = await self.bot.repo.delete_notification_route(gid, category.value)
            scope = "the category default"
        await interaction.response.send_message(f"Removed {scope}." if removed else f"No route was configured for {scope}.", ephemeral=True)

    @route_clear.autocomplete("title")
    async def route_clear_title_autocomplete(self, interaction: discord.Interaction, current: str):
        return await autocomplete_tracked_titles(interaction, current)

    def _validate_route_target(self, interaction, target: str, role, member, confirmation: str):
        if target == "role":
            if role is None or role.is_default() or role.managed:
                return False, "For a role target, choose a normal server role.", {}
            return True, "", {"target_mode": "role", "role_id": role.id, "user_id": None, "everyone_enabled": False}
        if target == "user":
            if member is None:
                return False, "For a user target, choose a server member.", {}
            return True, "", {"target_mode": "user", "role_id": None, "user_id": member.id, "everyone_enabled": False}
        if target == "everyone":
            if not interaction.user.guild_permissions.administrator:
                return False, "Only server administrators may configure @everyone routes.", {}
            if confirmation.strip().upper() != "ENABLE":
                return False, "To enable @everyone for this route, enter `ENABLE` in the confirmation field.", {}
            return True, "", {"target_mode": "everyone", "role_id": None, "user_id": None, "everyone_enabled": True}
        return True, "", {"target_mode": "none", "role_id": None, "user_id": None, "everyone_enabled": False}

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

    @notify.command(name="channel", description="Set the server-wide fallback channel for release notifications")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if channel.guild.id != gid:
            await interaction.response.send_message("Choose a text channel from this server.", ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "notification_channel_id", channel.id)
        await interaction.response.send_message(f"Notification channel set to {channel.mention}.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @notify.command(name="target", description="Choose the server-wide default: no ping, role, user, or everyone")
    @app_commands.choices(target=TARGET_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def target(self, interaction: discord.Interaction, target: app_commands.Choice[str]):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        settings = await self.bot.repo.ensure_guild(gid)
        if target.value == "everyone" and not settings.get("everyone_enabled"):
            await interaction.response.send_message("@everyone pings are disabled. First run `/notify everyone enabled:true confirmation:ENABLE` to explicitly enable them.", ephemeral=True)
            return
        if target.value == "role" and not settings.get("target_role_id"):
            await interaction.response.send_message("Select a role first with `/notify role`.", ephemeral=True)
            return
        if target.value == "user" and not settings.get("target_user_id"):
            await interaction.response.send_message("Select a user first with `/notify user`.", ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "default_target", target.value)
        await interaction.response.send_message(f"Default notification target set to **{target.name}**.", ephemeral=True)

    @notify.command(name="role", description="Set the server-wide fallback role to ping for release notifications")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        if role.is_default() or role.managed:
            await interaction.response.send_message("Choose a normal server role, not @everyone or a managed integration role.", ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "target_role_id", role.id)
        await self.bot.repo.set_guild_setting(gid, "default_target", "role")
        await interaction.response.send_message(f"Notification target role set to {role.mention}.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @notify.command(name="user", description="Set the server-wide fallback member to ping for release notifications")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def user(self, interaction: discord.Interaction, member: discord.Member):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "target_user_id", member.id)
        await self.bot.repo.set_guild_setting(gid, "default_target", "user")
        await interaction.response.send_message(f"Notification target user set to {member.mention}.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @notify.command(name="everyone", description="Admin only: enable or disable server-wide @everyone notification pings")
    @app_commands.checks.has_permissions(administrator=True)
    async def everyone(self, interaction: discord.Interaction, enabled: bool, confirmation: str):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        expected = "ENABLE" if enabled else "DISABLE"
        if confirmation.strip().upper() != expected:
            await interaction.response.send_message(f"Confirmation did not match. Enter `{expected}` exactly to {'enable' if enabled else 'disable'} @everyone pings.", ephemeral=True)
            return
        await self.bot.repo.set_guild_setting(gid, "everyone_enabled", int(enabled))
        if enabled:
            await self.bot.repo.set_guild_setting(gid, "default_target", "everyone")
            message = "@everyone pings are explicitly enabled for this server. Only use this in a channel where everyone expects release alerts."
        else:
            settings = await self.bot.repo.get_guild(gid)
            if settings and settings.get("default_target") == "everyone":
                await self.bot.repo.set_guild_setting(gid, "default_target", "none")
            message = "@everyone pings are disabled."
        await interaction.response.send_message(message, ephemeral=True)

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
            "**1. Set a server-wide destination (admins):** `/notify channel` then `/notify role` if you want a default role ping.\n\n"
            "**2. Set a destination for one show:** `/notify show` — choose a tracked title and channel, then optionally choose a role. "
            "Leave role empty to send without a ping.\n\n"
            "**3. Test the show:** `/notify test-title` — sends a real test message through that show's episode/chapter route. "
            "If a role or user is configured, the test may ping them.\n\n"
            "Use `/notify title` to enable/disable all alerts for a title, `/notify types` to toggle episode/chapter alerts, "
            "and `/notify routes` to inspect the saved destinations. Existing advanced routing commands remain available."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @notify.command(name="preview", description="Send a server-default test notification; configured targets may be pinged")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction):
        gid = guild_id(interaction)
        if gid is None:
            await interaction.response.send_message(no_guild_message(), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success, message = await self.bot.notification_service.preview(gid)
        await interaction.followup.send(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(NotificationsCog(bot))
