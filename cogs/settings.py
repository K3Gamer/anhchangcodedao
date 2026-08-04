"""Cấu hình bot cho từng server."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from utils.constants import AUTOMOD_FEATURES, DEFAULT_PREFIX


class Settings(commands.Cog):
    """Nhóm lệnh cấu hình server (Admin)."""

    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name="prefix", description="Đổi prefix của bot trong server")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def prefix(self, interaction: discord.Interaction, prefix: str) -> None:
        prefix = prefix.strip()
        if not prefix or len(prefix) > 3:
            raise BotError("Prefix phải có từ 1 đến 3 ký tự.")
        if prefix.startswith("/"):
            raise BotError("Prefix không thể bắt đầu bằng `/`.")
        await self.bot.config_manager.update(interaction.guild.id, {"prefix": prefix})
        embed = self.bot.embeds.success(f"Prefix đã được đổi thành **{prefix}**.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setmodlog", description="Chọn kênh log quản trị (warn, kick, ban...)")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def setmodlog(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.config_manager.update(interaction.guild.id, {"mod_log_channel": channel.id})
        embed = self.bot.embeds.success(f"Kênh log quản trị: {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setlogging", description="Chọn kênh log sự kiện (join, leave, xóa tin nhắn...)")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def setlogging(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.config_manager.update(interaction.guild.id, {"logging_channel": channel.id})
        embed = self.bot.embeds.success(f"Kênh log sự kiện: {channel.mention}.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="settings", description="Xem cấu hình hiện tại của server")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def settings(self, interaction: discord.Interaction) -> None:
        config = await self.bot.config_manager.get(interaction.guild.id)
        embed = self.bot.embeds.base(
            title="⚙️ Cấu hình server",
            description=interaction.guild.name,
        )
        embed.add_field(name="Prefix", value=f"`{config.get('prefix', DEFAULT_PREFIX)}`")
        mod_log = config.get("mod_log_channel")
        embed.add_field(name="📜 Log quản trị", value=f"<#{mod_log}>" if mod_log else "Chưa đặt")
        logging_ch = config.get("logging_channel")
        embed.add_field(name="📜 Log sự kiện", value=f"<#{logging_ch}>" if logging_ch else "Chưa đặt")

        automod = config.get("automod", {})
        enabled_features = [
            f for f in AUTOMOD_FEATURES if automod.get(f, {}).get("enabled")
        ]
        embed.add_field(
            name="🛡️ AutoMod",
            value=", ".join(f"`{f}`" for f in enabled_features) if enabled_features else "Tắt hết",
            inline=False,
        )
        an = config.get("antinuke", {})
        embed.add_field(
            name="🚨 AntiNuke",
            value=f"{'Bật' if an.get('enabled') else 'Tắt'} • Hình phạt: **{an.get('action', 'ban')}**",
            inline=False,
        )
        ticket_cfg = config.get("ticket", {})
        staff_role = ticket_cfg.get("staff_role_id")
        embed.add_field(
            name="🎫 Ticket",
            value=f"Staff role: {f'<@&{staff_role}>' if staff_role else 'Chưa đặt'}",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Settings(bot))
