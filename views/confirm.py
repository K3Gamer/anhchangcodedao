"""View xác nhận (Yes/No) dùng chung cho các hành động nguy hiểm."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

import discord


class ConfirmButton(discord.ui.Button["ConfirmView"]):
    """Nút Xác nhận / Huỷ trong ConfirmView."""

    def __init__(self, kind: str, nonce: str, label: str, style: discord.ButtonStyle) -> None:
        super().__init__(label=label, style=style, custom_id=f"confirm_{kind}:{nonce}")
        self.kind = kind

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view.expected_user_id is not None and interaction.user.id != self.view.expected_user_id:
            await interaction.response.send_message(
                "Bạn không thể thao tác nút này.", ephemeral=True
            )
            return
        self.view.stop()
        if self.kind == "yes":
            if self.view.on_confirm is not None:
                await self.view.on_confirm(interaction)
            else:
                await interaction.response.edit_message(view=None)
        else:
            if self.view.on_cancel is not None:
                await self.view.on_cancel(interaction)
            else:
                await interaction.response.edit_message(view=None)


class ConfirmView(discord.ui.View):
    """Hộp thoại xác nhận không persistent (dùng cho hành động một lần).

    Chỉ người dùng kích hoạt mới được bấm nút (thông qua bind()).
    """

    def __init__(
        self,
        *,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        on_cancel: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        timeout: float = 60,
        confirm_label: str = "Xác nhận",
        cancel_label: str = "Huỷ",
    ) -> None:
        super().__init__(timeout=timeout)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.expected_user_id: int | None = None
        nonce = uuid4().hex[:8]
        self.add_item(ConfirmButton("yes", nonce, confirm_label, discord.ButtonStyle.success))
        self.add_item(ConfirmButton("no", nonce, cancel_label, discord.ButtonStyle.secondary))

    def bind(self, interaction: discord.Interaction) -> None:
        """Gắn người dùng kích hoạt — chỉ người này mới thao tác được nút."""
        self.expected_user_id = interaction.user.id
