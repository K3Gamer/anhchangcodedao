"""Hệ thống cảnh cáo (Warn) — lưu MongoDB."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_permissions
from core.errors import BotError
from database.warns import WarnRepository


class Warnings(commands.Cog):
    """Nhóm lệnh cảnh cáo dành cho Mod/Admin."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.repo = WarnRepository(bot.db)

    @app_commands.command(name="warn", description="Cảnh cáo một thành viên")
    @app_commands.describe(member="Thành viên cần cảnh cáo", reason="Lý do cảnh cáo")
    @require_permissions("moderate_members")
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Không có lý do",
    ) -> None:
        if member.id == interaction.user.id:
            raise BotError("Bạn không thể tự cảnh cáo chính mình.")
        doc = await self.repo.add(interaction.guild.id, member.id, interaction.user.id, reason)
        total = await self.repo.count(interaction.guild.id, member.id)
        embed = self.bot.embeds.success(
            f"Đã cảnh cáo **{member.display_name}**.\n"
            f"Mã cảnh cáo: `{doc['_id']}`\n"
            f"Tổng cảnh cáo: **{total}**"
        )
        await interaction.response.send_message(embed=embed)
        try:
            await member.send(
                embed=self.bot.embeds.warning(
                    f"Bạn đã bị cảnh cáo tại **{interaction.guild.name}**.\nLý do: {reason}"
                )
            )
        except discord.HTTPException:
            pass
        log_embed = self.bot.embeds.base(
            title="⚠️ Cảnh cáo",
            description=f"{interaction.user.mention} đã cảnh cáo {member.mention}\n"
                        f"Lý do: {reason}\nMã: `{doc['_id']}`",
        )
        await self.bot.send_log(interaction.guild, log_embed)

    @app_commands.command(name="unwarn", description="Gỡ một cảnh cáo (theo mã hoặc toàn bộ)")
    @app_commands.describe(
        member="Thành viên cần gỡ cảnh cáo",
        warn_id="Mã cảnh cáo cần gỡ (bỏ trống để gỡ toàn bộ)",
    )
    @require_permissions("moderate_members")
    async def unwarn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warn_id: str | None = None,
    ) -> None:
        if warn_id:
            removed = await self.repo.remove(interaction.guild.id, warn_id.strip().upper())
            if removed is None:
                raise BotError(f"Không tìm thấy cảnh cáo mã `{warn_id}`.")
            embed = self.bot.embeds.success(f"Đã gỡ cảnh cáo `{warn_id}` của **{member.display_name}**.")
        else:
            count = await self.repo.clear(interaction.guild.id, member.id)
            if count == 0:
                raise BotError(f"**{member.display_name}** không có cảnh cáo nào.")
            embed = self.bot.embeds.success(f"Đã xóa **{count}** cảnh cáo của **{member.display_name}**.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="✅ Gỡ cảnh cáo",
            description=f"{interaction.user.mention} đã gỡ cảnh cáo của {member.mention}",
        )
        await self.bot.send_log(interaction.guild, log_embed)

    @app_commands.command(name="warnings", description="Xem danh sách cảnh cáo của thành viên")
    @app_commands.describe(member="Thành viên cần xem cảnh cáo")
    @require_permissions("moderate_members")
    async def warnings(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        warns = await self.repo.get_all(interaction.guild.id, member.id)
        if not warns:
            raise BotError(f"**{member.display_name}** không có cảnh cáo nào.")
        embed = self.bot.embeds.base(
            title=f"⚠️ Cảnh cáo của {member.display_name}",
            description=f"Tổng: **{len(warns)}** cảnh cáo",
        )
        for warn in warns[:15]:
            moderator = interaction.guild.get_member(warn["moderator_id"])
            when = discord.utils.format_dt(warn["date"], "R") if warn.get("date") else "?"
            embed.add_field(
                name=f"`{warn['_id']}` — {when}",
                value=f"**Lý do:** {warn['reason']}\n"
                      f"**Bởi:** {moderator.mention if moderator else 'Không rõ'}",
                inline=False,
            )
        if len(warns) > 15:
            embed.add_field(name="…", value=f"Còn **{len(warns) - 15}** cảnh cáo khác.", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Warnings(bot))
