"""Thông báo kỳ thi Codeforces: tự động gửi khi có kỳ thi mới & nhắc sắp bắt đầu."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from database.codeforces import CodeforcesRepository
from services.codeforces import CodeforcesService

logger = logging.getLogger("codi")

# Quét API Codeforces mỗi 5 phút
CF_CHECK_INTERVAL = 300


class Codeforces(commands.Cog):
    """Nhóm lệnh & vòng lặp nền thông báo kỳ thi Codeforces."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.repo = CodeforcesRepository(bot.db)
        self.service = CodeforcesService(bot, self.repo)
        self._task: asyncio.Task[None] | None = None

    # ================================================================
    # Background loop
    # ================================================================
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def cog_unload(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await self.service.check()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Lỗi trong vòng lặp thông báo Codeforces")
            try:
                await asyncio.sleep(CF_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    # ================================================================
    # Nhóm lệnh /cf
    # ================================================================
    cf = app_commands.Group(name="cf", description="Lệnh liên quan đến kỳ thi Codeforces")

    @cf.command(name="setup", description="Bật thông báo kỳ thi Codeforces cho server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Kênh gửi thông báo (mặc định kênh hiện tại)",
        role="Role được ping khi có kỳ thi mới (tùy chọn)",
    )
    @is_admin()
    async def cf_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        role: discord.Role | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            raise BotError("Kênh không hợp lệ. Hãy chỉ định một kênh văn bản.")

        updates: dict[str, object] = {"enabled": True, "channel_id": target.id}
        if role is not None:
            updates["ping_role_id"] = role.id
        await self.repo.update(interaction.guild.id, updates)
        await self.service.seed(interaction.guild.id)

        role_text = role.mention if role else "Không có"
        embed = self.bot.embeds.success(
            f"Đã bật thông báo kỳ thi Codeforces tại {target.mention}.\n"
            f"Role ping: {role_text}\n"
            "Bot sẽ thông báo khi có kỳ thi mới và nhắc **1 giờ** trước giờ thi."
        )
        await interaction.response.send_message(embed=embed)

    @cf.command(name="fcontest", description="Gửi thông báo kỳ thi CF gần nhất vào kênh CF")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Kênh nhận thông báo (mặc định: kênh đã cấu hình / kênh có tên CF)",
        ping="Ping @everyone khi gửi (tùy chọn)",
    )
    @is_admin()
    async def cf_fcontest(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        ping: bool = False,
    ) -> None:
        contest = await self.service.get_next()
        if contest is None:
            raise BotError("Hiện không có kỳ thi Codeforces nào sắp diễn ra.")

        target = channel or await self._resolve_cf_channel(interaction)
        if target is None:
            raise BotError("Chưa có kênh CF. Hãy chỉ định kênh (vd: `/cf fcontest #codeforces`) hoặc chạy `/cf setup` trước.")

        embed = self.service.build_fcontest_embed(contest)
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="🎮 Tham gia",
                url=f"https://codeforces.com/contestRegistration/{contest['id']}",
            )
        )
        await target.send(content="@everyone" if ping else None, embed=embed, view=view)
        embed = self.bot.embeds.success(f"Đã gửi thông báo kỳ thi đến {target.mention}.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _resolve_cf_channel(
        self, interaction: discord.Interaction
    ) -> discord.TextChannel | None:
        """Chọn kênh CF: ưu tiên kênh đã cấu hình, rồi kênh có tên chứa 'cf'/'codeforces'."""
        doc = await self.repo.get(interaction.guild.id)
        channel_id = doc.get("channel_id")
        if channel_id:
            ch = interaction.guild.get_channel(channel_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        for ch in interaction.guild.text_channels:
            if "cf" in ch.name.lower() or "codeforces" in ch.name.lower():
                return ch
        return None

    @cf.command(name="off", description="Tắt thông báo kỳ thi Codeforces cho server")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def cf_off(self, interaction: discord.Interaction) -> None:
        await self.repo.update(interaction.guild.id, {"enabled": False})
        embed = self.bot.embeds.success("Đã tắt thông báo kỳ thi Codeforces.")
        await interaction.response.send_message(embed=embed)

    @cf.command(name="settings", description="Xem cấu hình thông báo Codeforces của server")
    async def cf_settings(self, interaction: discord.Interaction) -> None:
        doc = await self.repo.get(interaction.guild.id)
        enabled = bool(doc.get("enabled"))
        channel_id = doc.get("channel_id")
        role_id = doc.get("ping_role_id")

        embed = self.bot.embeds.base(
            title="⚙️ Cấu hình Codeforces",
            description=interaction.guild.name,
        )
        embed.add_field(
            name="🔔 Trạng thái",
            value="**Bật**" if enabled else "**Tắt**",
        )
        embed.add_field(name="📢 Kênh", value=f"<#{channel_id}>" if channel_id else "Chưa đặt")
        embed.add_field(
            name="📣 Role ping",
            value=f"<@&{role_id}>" if role_id else "Không có",
        )
        embed.add_field(
            name="⏰ Nhắc",
            value="1 giờ trước giờ thi",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @cf.command(name="contests", description="Xem các kỳ thi Codeforces sắp diễn ra")
    async def cf_contests(self, interaction: discord.Interaction) -> None:
        embed, contests = await self.service.build_upcoming_embed()
        if embed is None:
            embed = self.bot.embeds.info("Hiện không có kỳ thi Codeforces nào sắp diễn ra.")
        else:
            embed.set_footer(
                text=f"Cập nhật từ Codeforces API • {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url,
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Codeforces(bot))