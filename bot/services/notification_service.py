from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

import discord

from ..database.repositories import Repository
from ..utils.embeds import release_embed

log = logging.getLogger(__name__)

EVENT_PREF = {
    "episode_window_passed": "notify_episodes",
    "upcoming_episode": "notify_episodes",
    "new_episode": "notify_episodes",
    "new_chapter": "notify_chapters",
    "schedule_change": "notify_schedule",
    "delay": "notify_delays",
    "hiatus": "notify_hiatus",
    "cancelled": "notify_announcements",
    "return": "notify_hiatus",
    "new_season": "notify_announcements",
    "official_announcement": "notify_announcements",
    "news_report": "notify_announcements",
}


class NotificationService:
    def __init__(self, repo: Repository, bot: discord.Client):
        self.repo = repo
        self.bot = bot

    async def preview(self, guild_id: int) -> tuple[bool, str]:
        settings = await self.repo.get_guild(guild_id)
        if not settings or not settings.get("notification_channel_id"):
            return False, "Set a title notification route with `/notify show` first."
        channel = self.bot.get_channel(int(settings["notification_channel_id"]))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(settings["notification_channel_id"]))
            except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                return False, "I cannot access that channel. Check that it still exists and that the bot can view and send messages there."
        fake = {"title": "Notification preview", "format": "ANIME", "update_type": "preview", "number": None,
                "release_at": None, "status": "unverified", "source": "Local test", "url": "https://anilist.co/", "summary": "This is a preview; no release was reported."}
        content, allowed = self._mention_payload(settings, None)
        try:
            message = await channel.send(content=content, embed=release_embed(fake), allowed_mentions=allowed)
            return True, f"Preview sent successfully (message ID {message.id})."
        except (discord.HTTPException, discord.Forbidden) as exc:
            return False, f"Discord could not send the preview: {type(exc).__name__}. Check channel permissions."

    async def preview_title(self, guild_id: int, track: dict[str, Any], guild: discord.Guild | None = None) -> tuple[bool, str]:
        """Send a real test message using the same title/category route as a release alert.

        This intentionally does not create a release event or notification-history row.
        If title notifications are disabled, it reports the blocker instead of sending a
        misleading test ping.
        """
        media_format = str(track.get("format") or "ANIME").upper()
        category = "chapters" if media_format == "MANGA" else "episodes"
        preference = "notify_chapters" if category == "chapters" else "notify_episodes"
        if not bool(track.get("notifications_enabled", 1)):
            return False, f"**{track.get('title', 'This title')}** is disabled for notifications. No test message was sent. Enable it with `/notify title` first."
        if not bool(track.get(preference, 1)):
            return False, f"Episode/chapter alerts are disabled for **{track.get('title', 'this title')}**. No test message was sent. Enable them with `/notify types`."

        settings = await self.repo.get_guild(guild_id) or {}
        route = await self.repo.get_notification_route(
            guild_id, category, provider=str(track.get("provider")), external_id=str(track.get("external_id"))
        )
        if route:
            effective = dict(settings)
            effective.update(route)
            effective["default_target"] = route.get("target_mode", "none")
            effective["target_role_id"] = route.get("role_id")
            effective["target_user_id"] = route.get("user_id")
            effective["everyone_enabled"] = route.get("everyone_enabled", 0)
            channel_id = route.get("channel_id")
            route_description = "title-specific route" if route.get("scope") == "title" else "category default route"
        else:
            effective = dict(settings)
            channel_id = settings.get("notification_channel_id")
            route_description = "server default settings"
        if not channel_id:
            return False, (f"No channel is configured for **{track.get('title', 'this title')}**. "
                           "Use `/notify show` to set a channel and optional role for this title.")

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                return False, "I can't access the configured notification channel. Check that it still exists and that the bot can view and send messages there."
        if not hasattr(channel, "send"):
            return False, "The configured destination isn't a message channel. Choose a server text channel."

        target = str(effective.get("target_mode") or effective.get("default_target") or "none")
        if target == "role":
            role_id = effective.get("target_role_id")
            if not role_id:
                return False, "The notification target is set to Role, but no role is selected. Run `/notify show` to choose one."
            if guild is not None:
                role = guild.get_role(int(role_id))
                if role is None:
                    return False, "The configured role no longer exists in this server. Run `/notify show` to select a valid role."
                bot_member = guild.me
                if not role.mentionable and bot_member is not None:
                    permissions = channel.permissions_for(bot_member) if hasattr(channel, "permissions_for") else None
                    if permissions is not None and not permissions.mention_everyone:
                        return False, (f"The route is set to ping {role.mention}, but that role isn't mentionable and the bot lacks "
                                       "the permission to mention all roles. Enable **Allow anyone to @mention this role** for that role, "
                                       "or grant the bot the **Mention @everyone, @here, and All Roles** permission. No test message was sent.")
        if target == "user":
            user_id = effective.get("target_user_id")
            if not user_id:
                return False, "The notification target is set to User, but no user is selected. Run `/notify show` to choose a valid notification route."
            if guild is not None and guild.get_member(int(user_id)) is None:
                try:
                    await guild.fetch_member(int(user_id))
                except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                    return False, "The configured user is no longer available in this server. Update the notification target first."

        content, allowed = self._mention_payload(effective, None)
        mention_text = {"none": "no ping", "role": "role ping", "user": "user ping", "everyone": "@everyone ping"}.get(target, "no ping")
        if content is None:
            mention_text = "no ping (target disabled or incomplete)"
        embed = discord.Embed(
            title=f"Notification test: {track.get('title', 'Tracked title')}",
            description=(f"This is a test of the **{category}** notification route. "
                         "No new episode or chapter has been reported; this message does not create a release event."),
            color=discord.Color.blurple(),
        )
        url = track.get("url")
        if url and str(url).startswith(("https://", "http://")):
            embed.url = str(url)
        embed.add_field(name="Route", value=route_description, inline=True)
        embed.add_field(name="Expected mention", value=mention_text, inline=True)
        try:
            message = await channel.send(content=content, embed=embed, allowed_mentions=allowed)
        except (discord.HTTPException, discord.Forbidden) as exc:
            log.warning("Title notification test failed for guild %s: %s", guild_id, type(exc).__name__)
            return False, "Discord couldn't send the test. Check the bot's View Channel, Send Messages, Embed Links, and role-mention permissions."
        return True, (f"Test sent to <#{channel_id}> using the {route_description}. "
                      f"Configured target: **{mention_text}**. Message ID: `{message.id}`. "
                      "If a role/user is configured, this test can send a real ping.")

    async def dispatch_pending(self, max_events: int = 500) -> int:
        events = await self.repo.list_pending_events(int(time.time()) - 48 * 3600, max_events)
        sends = 0
        sent_by_guild: dict[int, int] = {}
        per_guild_limit = 5
        for event in reversed(events):
            tracks = await self.repo.list_guilds_tracking(event["provider"], event["external_id"])
            for track in tracks:
                guild_id = int(track["guild_id"])
                if sent_by_guild.get(guild_id, 0) >= per_guild_limit:
                    continue
                if not track.get("notifications_enabled", 1):
                    continue
                pref = EVENT_PREF.get(event["update_type"])
                if pref and not track.get(pref, 1):
                    continue
                category = _route_category(event["update_type"], event.get("format"))
                route = await self.repo.get_notification_route(
                    guild_id, category, provider=event["provider"], external_id=str(event["external_id"])
                )
                effective = dict(track)
                if route:
                    effective.update(route)
                    # Route-specific values take precedence, including an explicit no-ping.
                    effective["default_target"] = route.get("target_mode", "none")
                    effective["target_role_id"] = route.get("role_id")
                    effective["target_user_id"] = route.get("user_id")
                    effective["everyone_enabled"] = route.get("everyone_enabled", 0)
                if not effective.get("channel_id") and not effective.get("notification_channel_id"):
                    continue
                if _is_quiet(track, int(time.time())) and event["update_type"] not in {"official_announcement", "delay", "hiatus"}:
                    continue
                channel_id = int(effective.get("channel_id") or effective["notification_channel_id"])
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                        continue
                # Don't let title/news text choose mentions; only configured guild settings are consulted.
                content, allowed = self._mention_payload(effective, event)
                reserved = await self.repo.reserve_notification(guild_id, event["release_key"], channel_id)
                if not reserved:
                    continue
                try:
                    msg = await channel.send(content=content, embed=release_embed(event), allowed_mentions=allowed)
                    await self.repo.finish_notification(guild_id, event["release_key"], "sent", msg.id)
                    sends += 1
                    sent_by_guild[guild_id] = sent_by_guild.get(guild_id, 0) + 1
                except (discord.HTTPException, discord.Forbidden) as exc:
                    await self.repo.finish_notification(guild_id, event["release_key"], "failed")
                    log.warning("Discord notification failed for guild %s: %s", guild_id, type(exc).__name__)
        return sends

    def _mention_payload(self, settings: dict[str, Any], event: dict[str, Any] | None) -> tuple[str | None, discord.AllowedMentions]:
        target = str(settings.get("target_mode") or settings.get("default_target") or "none")
        if target == "role" and settings.get("target_role_id"):
            role_id = int(settings["target_role_id"])
            return f"<@&{role_id}>", discord.AllowedMentions(everyone=False, users=False, roles=[discord.Object(id=role_id)], replied_user=False)
        if target == "user" and settings.get("target_user_id"):
            user_id = int(settings["target_user_id"])
            return f"<@{user_id}>", discord.AllowedMentions(everyone=False, users=[discord.Object(id=user_id)], roles=False, replied_user=False)
        if target == "everyone" and bool(settings.get("everyone_enabled")):
            # The setting can only be enabled through an administrator-guarded command.
            return "@everyone", discord.AllowedMentions(everyone=True, users=False, roles=False, replied_user=False)
        return None, discord.AllowedMentions.none()


def _is_quiet(settings: dict[str, Any], now: int) -> bool:
    start, end = settings.get("quiet_start"), settings.get("quiet_end")
    if not start or not end:
        return False
    try:
        zone = ZoneInfo(str(settings.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    local = datetime.fromtimestamp(now, zone).strftime("%H:%M")
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def _route_category(update_type: str, media_format: str | None = None) -> str:
    """Map release/news event types to configurable routing categories."""
    if update_type in {"new_chapter"} or (media_format == "MANGA" and update_type in {"episode_window_passed", "upcoming_episode", "new_episode"}):
        return "chapters"
    if update_type in {"upcoming_episode", "new_episode", "episode_window_passed"}:
        return "episodes"
    if update_type in {"schedule_change", "delay"}:
        return "schedule"
    return "news"
