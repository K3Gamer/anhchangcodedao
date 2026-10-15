"""Lệnh dành riêng cho chủ sở hữu bot."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import COGS
from core.checks import is_bot_owner
from core.errors import BotError
from services.runner import WORKFLOW_FILE
from views.confirm import ConfirmView

logger = logging.getLogger("codi")


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

    # ------------------------------------------------------------------
    # /restart — chạy lại workflow GitHub Actions đang host bot
    # ------------------------------------------------------------------
    @app_commands.command(
        name="restart",
        description="Chạy lại bot (đẩy dữ liệu → tạo GitHub Action run mới → huỷ run cũ)",
    )
    @app_commands.describe(force="Không hỏi lại, chạy ngay (nguy hiểm: bot sẽ offline ~15s)")
    @is_bot_owner()
    async def restart(self, interaction: discord.Interaction, force: bool = False) -> None:
        runner = getattr(self.bot, "runner_service", None)
        if runner is None or not runner.available:
            embed = self.bot.embeds.error(
                "Lệnh này chỉ chạy được trên GitHub Actions "
                "(thiếu biến môi trường `GITHUB_TOKEN` hoặc `GITHUB_REPOSITORY`)."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        info = (
            f"Repo: `{runner.repo}`\n"
            f"Workflow: `{WORKFLOW_FILE}`\n\n"
            "Bot sẽ **offline khoảng 15–30 giây**. Dữ liệu XP/config sẽ được "
            "đẩy lên nhánh `data` trước khi restart để không mất gì."
        )
        if not force:
            view = ConfirmView(
                on_confirm=lambda i: self._confirm_restart(i, runner),
                confirm_label="Chạy lại bot",
                timeout=60,
            )
            view.bind(interaction)
            await interaction.followup.send(
                embed=self.bot.embeds.warning(info, title="♻️ Chạy lại bot"),
                view=view,
                ephemeral=True,
            )
            return

        await self._confirm_restart(interaction, runner)

    async def _confirm_restart(self, interaction: discord.Interaction, runner) -> None:
        """Đẩy dữ liệu, tạo run mới, rồi huỷ run hiện tại (nơi bot đang chạy)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            # 1. Đẩy dữ liệu trước: nếu bước này hỏng thì bot vẫn sống và
            #    không mất XP/config. Huỷ run sẽ giết tiến trình, mất dữ liệu RAM.
            await interaction.followup.send(
                embed=self.bot.embeds.info("Đang đẩy dữ liệu lên nhánh `data`..."),
                ephemeral=True,
            )
            await runner.push_data()
        except BotError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error(
                    f"{exc}\n\n**Đã huỷ restart** để không mất dữ liệu. Bot vẫn đang chạy."
                ),
                ephemeral=True,
            )
            return

        # 2. Tạo run mới TRƯỚC khi huỷ run hiện tại — ngược lại sẽ không có gì
        #    để chờ, và bot sẽ không tự quay lại.
        try:
            await interaction.followup.send(
                embed=self.bot.embeds.info("Đang tạo GitHub Action run mới..."),
                ephemeral=True,
            )
            await runner.dispatch()
        except BotError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error(
                    f"{exc}\n\n**Đã huỷ restart.** Bot vẫn đang chạy bình thường."
                ),
                ephemeral=True,
            )
            return

        cancelled = False
        try:
            cancelled = await runner.cancel_current_run()
        except BotError as exc:
            logger.error("Không huỷ được run hiện tại: %s", exc)

        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Đã đẩy dữ liệu và tạo run mới.\n"
                "Bot sẽ tự tắt ngay — run mại sẽ khởi động lại bot trong khoảng 15–30 giây."
                + ("" if cancelled else "\n\n⚠️ Không huỷ được run hiện tại; nếu bot không tắt, hãy dừng thủ công trong tab Actions.")
                + f"\n\nTheo dõi tại: {runner.actions_url}",
                title="♻️ Đang khởi động lại",
            ),
            ephemeral=True,
        )

        # Run mới đã được tạo và đang chờ -> đóng bot để runner dọn dẹp,
        # giải phóng concurrency group cho run mới bắt đầu.
        try:
            await self.bot.close()
        finally:
            logger.info("Đã đóng bot sau /restart (run mới sẽ tự khởi động lại).")


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Owner(bot))
