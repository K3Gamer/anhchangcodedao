"""Hệ thống XP & bảng xếp hạng: cộng XP khi nhắn tin, lệnh /rank và /leaderboard."""

from __future__ import annotations

import io
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin

logger = logging.getLogger("codi")


class Leveling(commands.Cog):
    """Tính XP theo hoạt động và hiển thị bảng xếp hạng."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service: Any = bot.leveling_service

    # ================================================================
    # Sự kiện: cộng XP mỗi tin nhắn
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            return
        if self.service is None:
            return
        try:
            result = await self.service.grant_xp(message.guild.id, message.author.id)
            # Thông báo updater nếu XP thực sự thay đổi
            if result is not None:
                updater = getattr(self.bot, "leaderboard_updater", None)
                if updater:
                    await updater.notify_xp_change(message.guild.id)
        except Exception:
            logger.exception("Lỗi khi cộng XP cho %s", message.author.id)

    # ================================================================
    # /rank — thẻ level của thành viên (ảnh)
    # ================================================================
    @app_commands.command(
        name="rank", description="Xem thẻ cấp độ XP của bạn hoặc người khác"
    )
    @app_commands.describe(member="Thành viên cần xem (mặc định: bạn)")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        if member.bot:
            embed = self.bot.embeds.error("Bot không có XP hoạt động.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        doc = await self.service.get_user(interaction.guild_id, member.id)
        if doc is None:
            level = 0
            xp = 0
            rank = 0
        else:
            level = doc["level"]
            xp = doc.get("total_xp", 0)
            rank = doc["rank"]

        xp_in_level, xp_to_next, _, _ = self.service.level_progress(xp)

        image = await self._render_rank_card(member, level, xp, rank)
        file = discord.File(io.BytesIO(image), filename="rank.png")

        # Số thứ hạng hợp lệ
        rank_display = rank if rank and rank > 0 else "#—"
        embed = self.bot.embeds.base(
            title=f"🏆 Cấp độ của {member.display_name}",
            description=(
                f"**Cấp độ:** `{level}`\n"
                f"**Tổng XP:** `{xp:,}`\n"
                f"**Tiến trình:** `{xp_in_level:,}/{xp_to_next:,}` XP\n"
                f"**Thứ hạng:** `{rank_display}`"
            ),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, file=file)

    # ================================================================
    # /leaderboard — bảng xếp hạng ảnh đẹp
    # ================================================================
    @app_commands.command(
        name="leaderboard", description="Xem bảng xếp hạng XP hình ảnh của server"
    )
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        top_docs = await self.service.get_top(interaction.guild_id, limit=10)
        if not top_docs:
            embed = self.bot.embeds.info(
                "Chưa có dữ liệu XP nào. Hãy hoạt động để bắt đầu tích lũy XP!"
            )
            await interaction.followup.send(embed=embed)
            return

        entries: list[tuple[str, str, int]] = []
        for doc in top_docs:
            if doc.get("total_xp", 0) <= 0:
                continue
            user = self.bot.get_user(doc.get("user_id", 0))
            if user:
                avatar = user.display_avatar.url
                if isinstance(user, discord.Member):
                    name = user.display_name
                else:
                    name = user.display_name if hasattr(user, "display_name") else user.name
            else:
                avatar = ""
                name = "Thành viên ẩn"
            entries.append((avatar, name, doc.get("total_xp", 0)))

        if not entries:
            embed = self.bot.embeds.info(
                "Chưa có thành viên nào có XP. Hãy hoạt động để bắt đầu tích lũy XP!"
            )
            await interaction.followup.send(embed=embed)
            return

        try:
            image = await self.service.build_leaderboard_image(
                interaction.guild_id, entries, top=3
            )
        except Exception:
            logger.exception("Không nạp được ảnh leaderboard")
            embed = self.bot.embeds.error("Không thể tạo ảnh bảng xếp hạng. Vui lòng thử lại.")
            await interaction.followup.send(embed=embed)
            return

        file = discord.File(io.BytesIO(image), filename="leaderboard.png")
        title = f"🏆 Bảng xếp hạng XP · {interaction.guild.name}"
        embed = self.bot.embeds.base(title=title)
        embed.set_image(url="attachment://leaderboard.png")
        await interaction.followup.send(embed=embed, file=file)

    # ================================================================
    # /rank reset — xóa dữ liệu XP (quản trị)
    # ================================================================
    @app_commands.command(
        name="rank-reset", description="[Quản trị] Xóa toàn bộ dữ liệu XP của server"
    )
    @is_admin()
    async def rank_reset(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        count = await self.service.reset_guild(interaction.guild_id)
        embed = self.bot.embeds.info(
            f"Đã xóa dữ liệu XP của **{count}** thành viên trong server."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ================================================================
    # Hỗ trợ — thẻ rank dạng ảnh riêng
    # ================================================================
    async def _render_rank_card(
        self, member: discord.Member, level: int, xp: int, rank: int
    ) -> bytes:
        from utils.leaderboard_image import LeaderboardRenderer

        renderer = LeaderboardRenderer()
        from services.leveling import LevelingService
        _, _, _, ratio = LevelingService.level_progress(xp)
        avatar = member.display_avatar.url
        rank_display = f"#{rank}" if rank and rank > 0 else "#—"
        return await renderer.render(
            [(avatar, member.display_name, xp, ratio)],
            top=0,
            title=f"Cấp độ {level} · Hạng {rank_display}",
        )


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Leveling(bot))
