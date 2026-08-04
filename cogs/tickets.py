"""Hệ thống Ticket Góp ý."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from services.ticket_service import TicketService
from views.tickets import TicketPanelView


class Tickets(commands.Cog):
    """Nhóm lệnh cài đặt & quản lý ticket."""

    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gopyticketsetup",
        description="Cài đặt hệ thống ticket Góp ý (Admin)",
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    @app_commands.describe(
        channel="Kênh đặt panel ticket (mặc định kênh hiện tại)",
        category="Danh mục chứa ticket (mặc định tự tạo)",
        staff_role="Role Staff được xem & trả lời ticket",
        transcript_channel="Kênh nhận transcript khi đóng ticket",
    )
    async def gopyticketsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        category: discord.CategoryChannel | None = None,
        staff_role: discord.Role | None = None,
        transcript_channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel
        if target is None or not isinstance(target, discord.TextChannel):
            raise BotError("Kênh không hợp lệ.")

        embed = self.bot.embeds.base(
            title="💡 Góp ý cho cộng đồng",
            description=(
                "Bạn có ý tưởng, đề xuất hoặc phản hồi nào cho cộng đồng **Code vì Đam Mê**?\n\n"
                "Hãy nhấn nút **💡 Góp ý** bên dưới để tạo một ticket riêng tư.\n"
                "Đội ngũ staff sẽ phản hồi bạn trong thời gian sớm nhất."
            ),
        )
        view = TicketPanelView(self.bot)
        message = await target.send(embed=embed, view=view)

        updates = {
            "ticket.panel_channel_id": target.id,
            "ticket.panel_message_id": message.id,
        }
        if category:
            updates["ticket.category_id"] = category.id
        if staff_role:
            updates["ticket.staff_role_id"] = staff_role.id
        if transcript_channel:
            updates["ticket.transcript_channel_id"] = transcript_channel.id
        await self.bot.config_manager.update(interaction.guild.id, updates)

        await interaction.response.send_message(
            embed=self.bot.embeds.success(f"✅ Panel ticket đã được gửi vào {target.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="closeticket", description="Đóng một ticket")
    @app_commands.describe(reason="Lý do đóng ticket")
    async def closeticket(
        self, interaction: discord.Interaction, reason: str | None = None
    ) -> None:
        service = TicketService(self.bot)
        await service.close_ticket(interaction, reason or "Không có lý do")


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Tickets(bot))
