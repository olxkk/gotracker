from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import discord

COLORS = {
    "scheduled": discord.Color.blurple(),
    "estimated": discord.Color.gold(),
    "officially_confirmed": discord.Color.green(),
    "verified": discord.Color.green(),
    "unverified": discord.Color.light_grey(),
    "preview": discord.Color.blurple(),
}


def clean_text(value: object, limit: int = 1000) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # External content must not be able to ping everyone, roles, or users.
    text = text.replace("@", "＠").replace("<", "‹").replace(">", "›")
    # Display feed/API text as plain prose, not user-supplied Discord markdown or link syntax.
    text = re.sub(r"([\\`*_{}\[\]()#+.!|~])", r"\\\1", text)
    return text[:limit]


def safe_http_url(value: object) -> str | None:
    try:
        parsed = urlparse(str(value or ""))
        if parsed.scheme in {"http", "https"} and parsed.netloc and len(str(value)) <= 1500:
            return str(value)
    except ValueError:
        pass
    return None


def release_embed(event: dict[str, Any]) -> discord.Embed:
    title = clean_text(event.get("title", "Release update"), 250) or "Release update"
    update_type = clean_text(str(event.get("update_type", "update")).replace("_", " ").title(), 100)
    status = str(event.get("status") or "unverified")
    url = safe_http_url(event.get("url"))
    embed = discord.Embed(title=title, url=url, description=clean_text(event.get("summary") or "No additional details supplied by source.", 1000),
                          color=COLORS.get(status, discord.Color.light_grey()))
    embed.add_field(name="Update", value=update_type or "Update", inline=True)
    number = event.get("number")
    if number is not None:
        label = "Episode" if str(event.get("format")).upper() == "ANIME" else "Chapter"
        embed.add_field(name=label, value=f"{number}", inline=True)
    stamp = event.get("release_at")
    if stamp:
        try:
            stamp = int(stamp)
            embed.add_field(name="Date / time", value=f"<t:{stamp}:F>\n<t:{stamp}:R> (Discord local time)", inline=False)
        except (TypeError, ValueError, OverflowError):
            embed.add_field(name="Date / time", value="Date not confirmed", inline=False)
    else:
        embed.add_field(name="Date / time", value="Unknown / not reliably available", inline=False)
    embed.add_field(name="Confirmation", value=status.replace("_", " ").title(), inline=True)
    embed.add_field(name="Source", value=clean_text(event.get("source") or "Unknown source", 100), inline=True)
    if url:
        embed.add_field(name="Source link", value=f"[Open source]({url})", inline=False)
    cover = safe_http_url(event.get("cover_url"))
    if cover:
        embed.set_thumbnail(url=cover)
    embed.set_footer(text="Dates and availability are only as reliable as the linked source.")
    return embed


def media_embed(media: dict[str, Any], provider_name: str | None = None) -> discord.Embed:
    title = clean_text(media.get("title", "Untitled"), 250)
    url = safe_http_url(media.get("url"))
    embed = discord.Embed(title=title, url=url, description=clean_text(media.get("description") or "No synopsis provided.", 1000), color=discord.Color.blurple())
    fmt = str(media.get("format") or "UNKNOWN")
    embed.add_field(name="Format", value=fmt.title(), inline=True)
    embed.add_field(name="Status", value=clean_text(media.get("status") or "Unknown", 100).replace("_", " ").title(), inline=True)
    if fmt == "ANIME":
        embed.add_field(name="Known episode count", value=str(media.get("episodes") if media.get("episodes") is not None else "Unknown"), inline=True)
        next_episode = media.get("next_episode")
        next_at = media.get("next_airing_at")
        if next_episode is not None and next_at:
            embed.add_field(name="Next scheduled airing", value=f"Episode {next_episode}\n<t:{int(next_at)}:F>\nScheduled; availability not verified", inline=False)
        else:
            embed.add_field(name="Next scheduled airing", value="No reliable schedule available", inline=False)
    else:
        embed.add_field(name="Catalogue chapter count", value=str(media.get("chapters") if media.get("chapters") is not None else "Unknown"), inline=True)
        embed.add_field(name="Latest chapter release", value="Not reliably available from metadata alone", inline=False)
    if media.get("start_date"):
        embed.add_field(name="Start date", value=clean_text(media["start_date"], 40), inline=True)
    if media.get("end_date"):
        embed.add_field(name="End date", value=clean_text(media["end_date"], 40), inline=True)
    if url:
        embed.add_field(name="Source", value=f"[Open {clean_text(provider_name or 'provider', 60)} entry]({url})", inline=False)
    cover = safe_http_url(media.get("cover_url"))
    if cover:
        embed.set_thumbnail(url=cover)
    return embed


def news_embed(item: dict[str, Any]) -> discord.Embed:
    title = clean_text(item.get("title") or "News", 250)
    url = safe_http_url(item.get("url"))
    embed = discord.Embed(title=title, url=url, description=clean_text(item.get("summary") or "No summary supplied by the feed.", 1000), color=discord.Color.green() if item.get("official") else discord.Color.light_grey())
    published = item.get("published_at")
    if published:
        embed.add_field(name="Announcement date", value=f"<t:{int(published)}:F>", inline=True)
    embed.add_field(name="Source", value=clean_text(item.get("source") or "Unknown", 100), inline=True)
    embed.add_field(name="Classification", value="Official feed" if item.get("official") else "Third-party / unverified report", inline=True)
    if url:
        embed.add_field(name="Link", value=f"[Open original]({url})", inline=False)
    return embed
