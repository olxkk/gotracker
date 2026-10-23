from __future__ import annotations

from typing import Any
import discord
from discord import app_commands

from ..providers.base import MediaTitle
from ..utils.embeds import clean_text, media_embed


def guild_id(interaction: discord.Interaction) -> int | None:
    return int(interaction.guild_id) if interaction.guild_id else None


def no_guild_message() -> str:
    return "This command is only available inside a Discord server."


async def autocomplete_tracked_titles(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []
    repo = interaction.client.repo
    tracks = await repo.list_tracks(int(interaction.guild_id))
    current_folded = current.casefold().strip()
    choices = []
    for track in tracks:
        name = str(track.get("title") or "")
        if current_folded and current_folded not in name.casefold():
            continue
        label = f"[{track.get('format','?')}] {name}"[:100]
        value = f"{track['provider']}:{track['external_id']}"
        choices.append(app_commands.Choice(name=label, value=value[:100]))
        if len(choices) >= 25:
            break
    return choices


async def resolve_track_argument(interaction: discord.Interaction, query: str) -> dict[str, Any] | None:
    """Resolve an autocomplete provider:id or a unique title in this guild."""
    if interaction.guild_id is None:
        return None
    repo = interaction.client.repo
    query = query.strip()
    if ":" in query:
        provider, external_id = query.split(":", 1)
        track = await repo.get_track(int(interaction.guild_id), provider, external_id)
        if track:
            return track
    matches = await repo.resolve_tracks(int(interaction.guild_id), query)
    exact = [x for x in matches if str(x.get("title", "")).casefold() == query.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    if len(matches) == 1:
        return matches[0]
    return None


def track_ambiguous_message() -> str:
    return "I could not identify exactly one tracked title. Use `/track list` or `/track search`, then choose the exact title."


class TrackResultSelect(discord.ui.Select):
    def __init__(self, cog: Any, guild_id_value: int, results: list[MediaTitle]):
        self.cog = cog
        self.guild_id_value = guild_id_value
        self.results = {(item.provider + ":" + item.external_id): item for item in results}
        options = []
        for item in results[:25]:
            label = f"[{item.format}] {item.title}"[:100]
            desc = f"{item.provider} · {item.status}"[:100]
            options.append(discord.SelectOption(label=label, value=f"{item.provider}:{item.external_id}", description=desc))
        super().__init__(placeholder="Choose the exact series…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        result = self.results.get(self.values[0])
        if result is None or interaction.guild_id != self.guild_id_value:
            await interaction.response.send_message("This selection is no longer valid. Run the command again.", ephemeral=True)
            return
        try:
            inserted, _ = await self.cog.bot.repo.add_track(self.guild_id_value, result)
        except Exception:
            await interaction.response.send_message("I couldn't save that title. Check the bot logs or try again.", ephemeral=True)
            return
        if inserted:
            content = f"Added or updated **{clean_text(result.title, 160)}** in this server's watchlist using **{clean_text(result.provider, 40)}**."
        else:
            content = f"**{clean_text(result.title, 160)}** is already tracked in this server using **{clean_text(result.provider, 40)}**."
        await interaction.response.edit_message(content=content, embed=media_embed(result.to_dict(), result.provider.title()), view=None)


class TrackResultView(discord.ui.View):
    def __init__(self, cog: Any, guild_id_value: int, results: list[MediaTitle]):
        super().__init__(timeout=120)
        self.add_item(TrackResultSelect(cog, guild_id_value, results))
