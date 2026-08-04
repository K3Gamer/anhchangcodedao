"""Lệnh dành riêng cho chủ sở hữu bot."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import COGS
from core.checks import is_bot_owner


class Owner(commands.Cog):
    """Nhóm lệnh bảo trì (chỉ chủ sở hữu bot)."""

    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name="reload", description="Tải lại một cog")
    @is_bot_owner()
    async def reload(self, interaction: discord.Interaction, cog: str) -> None:
        name = f"cogs.{cog.strip().lower()}"
        if name not in COGS:
            embed = self.bot.embeds.error(
                f"Cog không hợp lệ. Danh sách: {', '.join(c.rsplit('.', 1)[-1] for c in COGS)}"
            )
            await interaction.response.send_message(embed=embed)
            return
        try:
            await self.bot.reload_extension(name)
            embed = self.bot.embeds.success(f"Đã tải lại cog **{cog.strip().lower()}**.")
        except Exception as exc:
            embed = self.bot.embeds.error(f"Không tải lại được cog: {exc}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sync", description="Đồng bộ slash commands")
    @is_bot_owner()
    async def sync(self, interaction: discord.Interaction) -> None:
        try:
            synced = await self.bot.tree.sync()
            embed = self.bot.embeds.success(f"Đã đồng bộ **{len(synced)}** lệnh.")
        except Exception as exc:
            embed = self.bot.embeds.error(f"Đồng bộ thất bại: {exc}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shutdown", description="Tắt bot")
    @is_bot_owner()
    async def shutdown(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=self.bot.embeds.warning("Bot đang tắt..."))
        await self.bot.close()


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Owner(bot))
