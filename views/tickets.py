"""Persistent Views cho hệ thống Ticket — hoạt động kể cả khi bot restart."""

from __future__ import annotations

import discord

from core.errors import BotError
from services.ticket_service import TicketService


class TicketOpenButton(discord.ui.Button["TicketPanelView"]):
    """Nút mở Ticket Góp ý (persistent)."""

    def __init__(self) -> None:
        super().__init__(
            style=discord.ButtonStyle.primary,
            emoji="💡",
            label="Góp ý",
            custom_id="ticket_open",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        service = TicketService(interaction.client)
        try:
            await service.create_ticket(interaction)
        except BotError as exc:
            await self._send_error(interaction, str(exc))
        except Exception as exc:
            logger = interaction.client.logger
            logger.error("Lỗi tạo ticket: %s", exc, exc_info=True)
            await self._send_error(interaction, "Đã xảy ra lỗi không mong muốn.")

    @staticmethod
    async def _send_error(interaction: discord.Interaction, message: str) -> None:
        embed = interaction.client.embeds.error(message)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketPanelView(discord.ui.View):
    """Panel ticket góp ý (persistent, timeout=None)."""

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketOpenButton())


class TicketCloseButton(discord.ui.Button["TicketCloseView"]):
    """Nút đóng ticket (persistent) — mở modal xác nhận lý do."""

    def __init__(self) -> None:
        super().__init__(
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            label="Đóng ticket",
            custom_id="ticket_close",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Không thể thực hiện thao tác này ở đây.", ephemeral=True
            )
            return
        await interaction.response.send_modal(TicketCloseModal())


class TicketCloseView(discord.ui.View):
    """View chứa nút đóng ticket (persistent, timeout=None)."""

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketCloseButton())


class TicketCloseModal(discord.ui.Modal, title="Đóng ticket"):
    """Modal hỏi lý do trước khi đóng ticket."""

    reason = discord.ui.TextInput(
        label="Lý do đóng ticket (không bắt buộc)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Nhập lý do đóng ticket...",
    )

    def __init__(self) -> None:
        super().__init__(timeout=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        service = TicketService(interaction.client)
        try:
            await service.close_ticket(interaction, reason=self.reason.value or "Không có lý do")
        except BotError as exc:
            embed = interaction.client.embeds.error(str(exc))
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:
            logger = interaction.client.logger
            logger.error("Lỗi đóng ticket: %s", exc, exc_info=True)
