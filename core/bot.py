"""Lớp Bot chính: cấu hình intents, prefix, nạp cogs, xử lý lỗi toàn cục."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.config import load_config
from core.errors import BotError, MissingBotPermissionsError, NotBotOwnerError
from core.logging import setup_logging
from database.guild_config import GuildConfigManager
from utils.constants import DEFAULT_PREFIX
from utils.embeds import EmbedFactory
from views.tickets import TicketCloseView, TicketPanelView

logger = logging.getLogger("anhchangcodedao")

# Danh sách cog được nạp khi khởi động
COGS: tuple[str, ...] = (
    "cogs.general",
    "cogs.moderation",
    "cogs.warnings",
    "cogs.tickets",
    "cogs.automod",
    "cogs.antinuke",
    "cogs.logging",
    "cogs.settings",
    "cogs.owner",
)


class CodeDaoBot(commands.Bot):
    """Bot "Anh chàng Code dạo" — hỗ trợ prefix & slash command."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True          # cần cho join/leave, nickname, role
        intents.message_content = True  # cần cho prefix command & AutoMod
        intents.bans = True             # cần cho ban/unban
        intents.emojis_and_stickers = True
        intents.voice_states = True

        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="cộng đồng Code vì Đam Mê",
            ),
        )

        self.app_config = load_config()
        self.data_dir = self.app_config.data_dir
        self.embeds = EmbedFactory(self)
        self.config_manager: GuildConfigManager | None = None
        self.db = None
        self.start_time = datetime.now(timezone.utc)
        self.owner_ids: set[int] = set()

    # ------------------------------------------------------------------
    # Prefix
    # ------------------------------------------------------------------
    async def get_prefix(self, message: discord.Message) -> str | list[str]:
        """Prefix mặc định '!', có thể đổi theo từng server (lưu JSON)."""
        prefix = DEFAULT_PREFIX
        if self.config_manager is not None and message.guild is not None:
            try:
                config = await self.config_manager.get(message.guild.id)
                prefix = config.get("prefix") or DEFAULT_PREFIX
            except Exception:
                pass
        return commands.when_mentioned_or(prefix)(self, message)

    # ------------------------------------------------------------------
    # Khởi động
    # ------------------------------------------------------------------
    async def setup_hook(self) -> None:
        """Nạp toàn bộ cog, đăng ký Persistent Views và đồng bộ slash command."""
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info("Đã nạp cog: %s", cog)
            except Exception as exc:
                logger.error("Không nạp được cog %s: %s", cog, exc)

        # Đăng ký Persistent Views (hoạt động xuyên cả lần restart)
        self.add_view(TicketPanelView(self))
        self.add_view(TicketCloseView(self))

        await self.tree.sync()
        logger.info("Đã đồng bộ slash commands.")

    # ------------------------------------------------------------------
    # Dọn tin nhắn lệnh sau khi thực thi
    # ------------------------------------------------------------------
    async def after_invoke(self, ctx: commands.Context) -> None:
        """Xóa tin nhắn chứa lệnh (prefix) sau khi thực thi thành công."""
        if ctx.interaction is not None or ctx.guild is None:
            return
        message = ctx.message
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Gửi log tới kênh đã cấu hình
    # ------------------------------------------------------------------
    async def send_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        """Gửi embed log vào kênh logging/mod-log của server (nếu đã cấu hình)."""
        if self.config_manager is None:
            return
        try:
            config = await self.config_manager.get(guild.id)
            channel_id = config.get("logging_channel") or config.get("mod_log_channel")
            if not channel_id:
                return
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.send(embed=embed)
        except Exception:
            logger.exception("Không gửi được log cho guild %s", guild.id)

    # ------------------------------------------------------------------
    # Xử lý lỗi lệnh prefix
    # ------------------------------------------------------------------
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Chặn lỗi lệnh prefix: hiển thị thân thiện, không làm crash bot."""
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            embed = self.embeds.error(f"Bạn thiếu quyền: **{', '.join(error.missing_permissions)}**")
            return await self._safe_reply(ctx, embed)
        if isinstance(error, commands.BotMissingPermissions):
            embed = self.embeds.error(f"Bot thiếu quyền: **{', '.join(error.missing_permissions)}**")
            return await self._safe_reply(ctx, embed)
        if isinstance(error, commands.MissingRequiredArgument):
            embed = self.embeds.error(f"Thiếu tham số **{error.param.name}**.")
            return await self._safe_reply(ctx, embed)
        if isinstance(error, commands.BadArgument):
            embed = self.embeds.error(f"Tham số không hợp lệ: {error}")
            return await self._safe_reply(ctx, embed)
        if isinstance(error, commands.CommandOnCooldown):
            embed = self.embeds.warning(f"Lệnh đang hồi chiêu. Thử lại sau **{error.retry_after:.1f}s**.")
            return await self._safe_reply(ctx, embed)
        if isinstance(error, BotError):
            embed = self.embeds.error(str(error))
            return await self._safe_reply(ctx, embed)
        if isinstance(error, commands.CommandInvokeError):
            original = error.original
            if isinstance(original, BotError):
                embed = self.embeds.error(str(original))
                return await self._safe_reply(ctx, embed)

        # Lỗi không mong muốn
        self._log_unexpected(ctx.command, error)
        await self._report_error(ctx.guild, error)
        embed = self.embeds.error("Đã xảy ra lỗi không mong muốn. Vui lòng thử lại sau.")
        await self._safe_reply(ctx, embed)

    # ------------------------------------------------------------------
    # Xử lý lỗi lệnh slash
    # ------------------------------------------------------------------
    async def on_application_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Chặn lỗi lệnh slash: hiển thị thân thiện, không làm crash bot."""
        embed: discord.Embed | None = None

        if isinstance(error, app_commands.MissingPermissions):
            embed = self.embeds.error(f"Bạn thiếu quyền: **{', '.join(error.missing_permissions)}**")
        elif isinstance(error, MissingBotPermissionsError):
            embed = self.embeds.error(str(error))
        elif isinstance(error, NotBotOwnerError):
            embed = self.embeds.error("Chỉ chủ sở hữu bot mới dùng được lệnh này.")
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = self.embeds.warning(f"Lệnh đang hồi chiêu. Thử lại sau **{error.retry_after:.1f}s**.")
        elif isinstance(error, app_commands.CommandInvokeError):
            original = error.original
            if isinstance(original, BotError):
                embed = self.embeds.error(str(original))
            else:
                self._log_unexpected(interaction.command, original)
                await self._report_error(interaction.guild, original)
                embed = self.embeds.error("Đã xảy ra lỗi không mong muốn. Vui lòng thử lại sau.")
        elif isinstance(error, app_commands.CheckFailure):
            embed = self.embeds.error("Bạn không đủ quyền sử dụng lệnh này.")
        else:
            self._log_unexpected(interaction.command, error)
            await self._report_error(interaction.guild, error)
            embed = self.embeds.error(f"Đã xảy ra lỗi: {error}")

        if embed is None:
            return
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            except discord.HTTPException:
                pass
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Hỗ trợ xử lý lỗi
    # ------------------------------------------------------------------
    async def _safe_reply(self, ctx: commands.Context, embed: discord.Embed) -> None:
        """Reply embed, fallback sang send nếu reply lỗi."""
        try:
            await ctx.reply(embed=embed)
        except Exception:
            try:
                await ctx.send(embed=embed)
            except Exception:
                pass

    async def _report_error(self, guild: discord.Guild | None, error: Exception) -> None:
        """Ghi lỗi không mong muốn vào kênh log của server."""
        if guild is None or self.config_manager is None:
            return
        try:
            config = await self.config_manager.get(guild.id)
            channel_id = config.get("logging_channel") or config.get("mod_log_channel")
            if not channel_id:
                return
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                return
            embed = self.embeds.error(
                title="❌ Lỗi không mong muốn",
                description=f"```{error}```",
            )
            await channel.send(embed=embed)
        except Exception:
            pass

    @staticmethod
    def _log_unexpected(command: commands.Command | app_commands.Command | None, error: Exception) -> None:
        """Ghi lỗi bất ngờ vào logger (kèm traceback)."""
        name = getattr(command, "qualified_name", getattr(command, "name", "N/A"))
        logger.error(
            "Lỗi không mong muốn ở lệnh '%s': %s",
            name,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
