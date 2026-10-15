"""AutoX: tự động xóa tin nhắn của những thành viên được chỉ định."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError


class AutoX(commands.Cog):
    """Tự động xóa tin nhắn của thành viên nằm trong danh sách AutoX."""

    def __init__(self, bot) -> None:
        self.bot = bot

    # ================================================================
    # Listener chính
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Xóa ngay tin nhắn của thành viên nằm trong danh sách AutoX."""
        if message.author.bot or message.guild is None:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.guild.me is None or not message.guild.me.guild_permissions.manage_messages:
            return

        config = await self.bot.config_manager.get(message.guild.id)
        if message.author.id not in (config.get("autox") or []):
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass

    # ================================================================
    # Lệnh cấu hình
    # ================================================================
    @app_commands.command(
        name="autox",
        description="Tự động xóa tin nhắn của thành viên được chỉ định",
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.describe(member="Thành viên sẽ bị bot tự xóa tin nhắn")
    async def autox(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if member.bot:
            raise BotError("Không thể bật AutoX cho bot.")
        if member.id == interaction.user.id:
            raise BotError("Bạn không thể tự bật AutoX cho chính mình.")

        config = await self.bot.config_manager.get(interaction.guild.id)
        current = list(config.get("autox") or [])
        if member.id in current:
            current.remove(member.id)
            description = f"Đã **tắt** AutoX cho {member.mention}."
        else:
            current.append(member.id)
            description = (
                f"Đã **bật** AutoX cho {member.mention}.\n"
                "Mọi tin nhắn của thành viên này sẽ bị bot tự động xóa."
            )
        await self.bot.config_manager.update(interaction.guild.id, {"autox": current})

        listing = ", ".join(f"<@{uid}>" for uid in current[:20]) or "Chưa có"
        embed = self.bot.embeds.success(description)
        embed.add_field(name=f"Danh sách AutoX ({len(current)})", value=listing, inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(AutoX(bot))
