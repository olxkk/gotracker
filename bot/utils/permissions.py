from __future__ import annotations

import discord


def is_guild_admin(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and interaction.user and interaction.user.guild_permissions.manage_guild)


def require_guild(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None


def safe_mentions_none() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()
