"""Các decorator kiểm tra quyền cho lệnh slash và lệnh prefix."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.errors import MissingBotPermissionsError, NotBotOwnerError


def _missing_permissions(member: discord.Member, perms: tuple[str, ...]) -> list[str]:
    """Trả về danh sách quyền còn thiếu của một thành viên."""
    return [p for p in perms if not getattr(member.guild_permissions, p, False)]


def require_permissions(*perms: str) -> Callable[..., Any]:
    """Kiểm tra người dùng VÀ bot đều có đủ các quyền đã khai báo.

    Lệnh slash: thiếu quyền người dùng -> app_commands.MissingPermissions
                 thiếu quyền bot     -> MissingBotPermissionsError
    """
    def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member):
            missing_user = _missing_permissions(interaction.user, perms)
            if missing_user:
                raise app_commands.MissingPermissions(missing_user)
        if interaction.guild is not None:
            missing_bot = _missing_permissions(interaction.guild.me, perms)
            if missing_bot:
                raise MissingBotPermissionsError(missing_bot)
        return True

    return app_commands.check(predicate)


def is_admin() -> Callable[..., Any]:
    """Chỉ cho phép thành viên có quyền Administrator."""
    def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and not interaction.user.guild_permissions.administrator:
            raise app_commands.MissingPermissions(["administrator"])
        if interaction.guild is not None and not interaction.guild.me.guild_permissions.administrator:
            raise MissingBotPermissionsError(["administrator"])
        return True

    return app_commands.check(predicate)


def is_bot_owner() -> Callable[..., Any]:
    """Chỉ cho phép chủ sở hữu bot (owner_ids)."""
    def predicate(interaction: discord.Interaction) -> bool:
        owner_ids: set[int] = getattr(interaction.client, "owner_ids", None) or set()
        if interaction.user.id not in owner_ids:
            raise NotBotOwnerError
        return True

    return app_commands.check(predicate)


def require_prefix_permissions(*perms: str) -> Callable[..., Any]:
    """Kiểm tra quyền cho lệnh prefix (context)."""
    async def predicate(ctx: commands.Context) -> bool:
        missing_user = _missing_permissions(ctx.author, perms)
        if missing_user:
            raise commands.MissingPermissions(missing_user)
        missing_bot = _missing_permissions(ctx.me, perms)
        if missing_bot:
            raise commands.BotMissingPermissions(missing_bot)
        return True

    return commands.check(predicate)
