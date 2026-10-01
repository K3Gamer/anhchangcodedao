"""Hệ thống XP & bảng xếp hạng: cộng XP khi nhắn tin, lệnh /rank và /leaderboard."""

from __future__ import annotations

import io
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from services.leveling import LEADERBOARD_SIZE

logger = logging.getLogger("codi")

XP_CHANNELS_GROUP = "leveling.xp_channel_ids"


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
            if await self._is_command_message(message):
                return
            if not await self._xp_allowed_in(message.guild.id, message.channel.id):
                return
            result = await self.service.grant_xp(message.guild.id, message.author.id)
            # Thông báo updater nếu XP thực sự thay đổi
            if result is not None:
                await self._notify_leaderboard(message.guild.id, debounced=True)
        except Exception:
            logger.exception("Lỗi khi cộng XP cho %s", message.author.id)

    async def _is_command_message(self, message: discord.Message) -> bool:
        """Tin nhắn có phải lệnh prefix của bot không (thì không cộng XP).

        Chỉ bỏ qua khi lệnh thực sự tồn tại, nên tin nhắn thường bắt đầu bằng
        dấu "!" vẫn được tính XP bình thường.
        """
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if not any(p and message.content.startswith(p) for p in prefixes):
            return False
        try:
            ctx = await self.bot.get_context(message)
        except Exception:
            return True  # Không parse được thì coi như lệnh cho an toàn
        return ctx.command is not None

    async def _xp_allowed_in(self, guild_id: int, channel_id: int) -> bool:
        """Kênh này có được cộng XP không (danh sách rỗng nghĩa là mọi kênh)."""
        if self.bot.config_manager is None:
            return True
        try:
            config = await self.bot.config_manager.get(guild_id)
        except Exception:
            logger.exception("Không đọc được cấu hình XP channel của guild %s", guild_id)
            return True
        allowed = (config.get("leveling") or {}).get("xp_channel_ids") or []
        return not allowed or channel_id in allowed

    # ================================================================
    # Sự kiện: thành viên rời server -> bỏ khỏi bảng xếp hạng
    # ================================================================
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Bảng xếp hạng chỉ nên chứa thành viên đang ở trong server."""
        if member.bot or self.service is None:
            return
        try:
            await self._notify_leaderboard(member.guild.id)
        except Exception:
            logger.exception("Lỗi cập nhật leaderboard sau khi %s rời server", member.id)

    # ================================================================
    # Sự kiện: bot bị gỡ khỏi server -> dọn trạng thái
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        updater = getattr(self.bot, "leaderboard_updater", None)
        if updater is not None:
            updater.forget(guild.id)

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
            xp = int(doc.get("total_xp") or 0)
            rank = doc["rank"]

        xp_in_level, xp_to_next, _, _ = self.service.level_progress(xp)

        image = await self._render_rank_card(member, level, xp, rank)
        file = discord.File(io.BytesIO(image), filename="rank.png")

        # Số thứ hạng hợp lệ
        rank_display = f"#{rank}" if rank > 0 else "#—"
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

        try:
            entries, image = await self.service.render_leaderboard(
                interaction.guild, limit=LEADERBOARD_SIZE, top=3
            )
        except Exception:
            logger.exception("Không nạp được ảnh leaderboard")
            embed = self.bot.embeds.error("Không thể tạo ảnh bảng xếp hạng. Vui lòng thử lại.")
            await interaction.followup.send(embed=embed)
            return

        if not entries:
            embed = self.bot.embeds.info(
                "Chưa có ai tích lũy XP. Hãy hoạt động để bắt đầu tích luỹ XP!"
            )
            await interaction.followup.send(embed=embed)
            return

        file = discord.File(io.BytesIO(image), filename="leaderboard.png")
        title = f"🏆 Bảng xếp hạng XP · {interaction.guild.name}"
        embed = self.bot.embeds.base(title=title)
        embed.set_image(url="attachment://leaderboard.png")
        await interaction.followup.send(embed=embed, file=file)

    # ================================================================
    # /xp add — cộng XP thủ công
    # ================================================================
    @app_commands.command(
        name="xp-add", description="[Quản trị] Cộng XP cho thành viên"
    )
    @app_commands.describe(member="Thành viên cần cộng XP", amount="Số XP cần cộng")
    @is_admin()
    async def xp_add(
        self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 100000]
    ) -> None:
        if member.bot:
            embed = self.bot.embeds.error("Bot không có XP.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        doc = await self.service.add_xp(interaction.guild_id, member.id, amount)
        level = doc["level"]
        total = doc["total_xp"]
        embed = self.bot.embeds.success(
            f"Đã cộng **{amount:,} XP** cho {member.mention}\n"
            f"Tổng XP: **{total:,}** · Cấp độ: **{level}**"
        )
        await interaction.response.send_message(embed=embed)
        await self._notify_leaderboard(interaction.guild_id)

    # ================================================================
    # /xp remove — trừ XP thủ công
    # ================================================================
    @app_commands.command(
        name="xp-remove", description="[Quản trị] Trừ XP của thành viên"
    )
    @app_commands.describe(member="Thành viên cần trừ XP", amount="Số XP cần trừ")
    @is_admin()
    async def xp_remove(
        self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 100000]
    ) -> None:
        if member.bot:
            embed = self.bot.embeds.error("Bot không có XP.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        doc = await self.service.remove_xp(interaction.guild_id, member.id, amount)
        level = doc["level"]
        total = doc["total_xp"]
        embed = self.bot.embeds.success(
            f"Đã trừ **{amount:,} XP** của {member.mention}\n"
            f"Tổng XP: **{total:,}** · Cấp độ: **{level}**"
        )
        await interaction.response.send_message(embed=embed)
        await self._notify_leaderboard(interaction.guild_id)

    # ================================================================
    # /xp set — đặt XP thủ công
    # ================================================================
    @app_commands.command(
        name="xp-set", description="[Quản trị] Đặt XP cho thành viên"
    )
    @app_commands.describe(member="Thành viên cần đặt XP", amount="Tổng XP cần đặt")
    @is_admin()
    async def xp_set(
        self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 0, 1000000]
    ) -> None:
        if member.bot:
            embed = self.bot.embeds.error("Bot không có XP.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        doc = await self.service.set_xp(interaction.guild_id, member.id, amount)
        level = doc["level"]
        total = doc["total_xp"]
        embed = self.bot.embeds.success(
            f"Đã đặt XP của {member.mention} thành **{total:,} XP**\n"
            f"Cấp độ: **{level}**"
        )
        await interaction.response.send_message(embed=embed)
        await self._notify_leaderboard(interaction.guild_id)

    # ================================================================
    # /rank remove — xóa XP của 1 thành viên (quản trị)
    # ================================================================
    @app_commands.command(
        name="rank-remove", description="[Quản trị] Xóa dữ liệu XP của một thành viên"
    )
    @app_commands.describe(member="Thành viên cần xóa khỏi bảng xếp hạng")
    @is_admin()
    async def rank_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        doc = await self.service.get_user(interaction.guild_id, member.id)
        removed = await self.service.reset_user(interaction.guild_id, member.id)
        if not removed:
            embed = self.bot.embeds.info(
                f"{member.mention} hiện không có dữ liệu XP trong server này."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Bảng xếp hạng trong kênh phải cập nhật ngay để bỏ họ khỏi ảnh.
        await self._notify_leaderboard(interaction.guild_id)

        total = int((doc or {}).get("total_xp") or 0)
        level = (doc or {}).get("level", 0)
        embed = self.bot.embeds.success(
            f"Đã xóa **{total:,} XP** (cấp độ {level}) của {member.mention}.\n"
            "Thành viên này đã bị loại khỏi bảng xếp hạng."
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # /rank-reset — xóa dữ liệu XP của cả server (quản trị)
    # ================================================================
    @app_commands.command(
        name="rank-reset", description="[Quản trị] Xóa toàn bộ dữ liệu XP của server"
    )
    @is_admin()
    async def rank_reset(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        count = await self.service.reset_guild(interaction.guild_id)
        # Dữ liệu đã bị xoá -> bảng xếp hạng trong kênh phải cập nhật ngay,
        # nếu không sẽ còn treo ảnh của bảng xếp hạng cũ.
        await self._notify_leaderboard(interaction.guild_id)
        embed = self.bot.embeds.info(
            f"Đã xóa dữ liệu XP của **{count}** thành viên trong server."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ================================================================
    # Nhóm lệnh /xpchannels — chọn kênh nào được cộng XP
    # ================================================================
    xpchannels = app_commands.Group(
        name="xpchannels",
        description="Chọn kênh được cộng XP (mặc định: mọi kênh)",
        default_permissions=discord.Permissions(administrator=True),
    )

    @staticmethod
    def _format_channels(guild: discord.Guild, ids: list[int]) -> str:
        """Tên/mention của các kênh đã cấu hình, báo rõ nếu kênh đã bị xoá."""
        if not ids:
            return "Tất cả kênh"
        lines = []
        for cid in ids:
            channel = guild.get_channel(cid)
            lines.append(channel.mention if channel else f"`<#{cid}>` *(đã bị xoá)*")
        return "\n".join(lines)

    async def _read_xp_channels(self, guild_id: int) -> list[int]:
        config = await self.bot.config_manager.get(guild_id)
        raw = (config.get("leveling") or {}).get("xp_channel_ids") or []
        return [int(cid) for cid in raw]

    @xpchannels.command(name="show", description="Xem các kênh hiện được cộng XP")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def xpchannels_show(self, interaction: discord.Interaction) -> None:
        ids = await self._read_xp_channels(interaction.guild_id)
        embed = self.bot.embeds.base(
            title="📍 Kênh được cộng XP",
            description=(
                f"**Chế độ:** {'Mọi kênh' if not ids else 'Chỉ kênh đã chọn'}\n"
                f"**Số kênh:** `{len(ids)}`\n\n"
                f"{self._format_channels(interaction.guild, ids)}"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @xpchannels.command(
        name="list", description="Thêm hoặc gỡ một kênh khỏi danh sách cộng XP"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Thêm", value="add"),
            app_commands.Choice(name="Gỡ", value="remove"),
        ]
    )
    @app_commands.describe(
        action="Hành động",
        channel="Kênh muốn cộng XP (bỏ trống = dùng kênh hiện tại)",
    )
    @is_admin()
    async def xpchannels_list(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            raise BotError("Kênh không hợp lệ. Hãy chỉ định một kênh văn bản.")

        current = await self._read_xp_channels(interaction.guild_id)
        if action == "add":
            if target.id in current:
                raise BotError(f"{target.mention} đã có trong danh sách kênh cộng XP.")
            current.append(target.id)
            message = f"Đã thêm {target.mention} — chỉ cộng XP ở kênh này."
        else:
            if target.id not in current:
                raise BotError(
                    f"{target.mention} không có trong danh sách. "
                    "Dùng `/xpchannels reset` để cộng XP ở mọi kênh."
                )
            current.remove(target.id)
            message = (
                f"Đã gỡ {target.mention}.\n"
                + ("Giờ chỉ còn " + str(len(current)) + " kênh được cộng XP."
                   if current else "Danh sách trống → **mọi kênh** đều được cộng XP.")
            )

        await self.bot.config_manager.update(
            interaction.guild_id, {XP_CHANNELS_GROUP: current}
        )
        embed = self.bot.embeds.success(
            f"{message}\n\n{self._format_channels(interaction.guild, current)}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @xpchannels.command(name="reset", description="Cộng XP ở mọi kênh (bỏ giới hạn)")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def xpchannels_reset(self, interaction: discord.Interaction) -> None:
        await self.bot.config_manager.update(
            interaction.guild_id, {XP_CHANNELS_GROUP: []}
        )
        embed = self.bot.embeds.success(
            "Đã bỏ giới hạn: **mọi kênh** đều được cộng XP."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # Hỗ trợ — thông báo updater leaderboard
    # ================================================================
    async def _notify_leaderboard(self, guild_id: int, debounced: bool = False) -> None:
        """Báo cho updater biết bảng xếp hạng cần cập nhật."""
        updater = getattr(self.bot, "leaderboard_updater", None)
        if updater is None:
            return
        if debounced:
            await updater.notify_xp_change(guild_id)
        else:
            await updater.force_update(guild_id)

    # ================================================================
    # Hỗ trợ — thẻ rank dạng ảnh riêng
    # ================================================================
    async def _render_rank_card(
        self, member: discord.Member, level: int, xp: int, rank: int
    ) -> bytes:
        _, _, _, ratio = self.service.level_progress(xp)
        rank_display = f"#{rank}" if rank > 0 else "#—"
        return await self.service.build_leaderboard_image(
            member.guild.id,
            [(member.display_avatar.url, member.display_name, xp)],
            top=0,
            title=f"Cấp độ {level} · Hạng {rank_display}",
        )


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Leveling(bot))
