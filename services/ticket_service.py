"""Nghiệp vụ hệ thống Ticket: tạo ticket, đóng ticket, transcript."""

from __future__ import annotations

import logging

import discord

from core.errors import BotError
from database.tickets import TicketRepository
from services.transcript import generate_transcript
from utils.text import slugify

logger = logging.getLogger("codi")

TICKET_LABEL: dict[str, str] = {
    "gopy": "💡 Góp ý",
}


class TicketService:
    """Tầng nghiệp vụ cho toàn bộ luồng Ticket."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.repo = TicketRepository(bot.db)

    # ------------------------------------------------------------------
    # Tiện ích nội bộ
    # ------------------------------------------------------------------
    async def _get_staff_role(self, guild: discord.Guild) -> discord.Role | None:
        config = await self.bot.config_manager.get(guild.id)
        role_id = config.get("ticket", {}).get("staff_role_id")
        return guild.get_role(role_id) if role_id else None

    @staticmethod
    def _is_staff(member: discord.Member, staff_role: discord.Role | None) -> bool:
        if staff_role is not None and staff_role in member.roles:
            return True
        return member.guild_permissions.manage_channels or member.guild_permissions.administrator

    # ------------------------------------------------------------------
    # Tạo ticket
    # ------------------------------------------------------------------
    async def create_ticket(self, interaction: discord.Interaction) -> None:
        """Tạo kênh ticket riêng tư chỉ Staff và người tạo nhìn thấy."""
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            raise BotError("Không thể tạo ticket ở đây.")

        config = await self.bot.config_manager.get(guild.id)

        # Mỗi người chỉ được mở tối đa 1 ticket cùng lúc
        existing = await self.repo.get_by_user(guild.id, interaction.user.id)
        if existing:
            channel = guild.get_channel(existing["_id"])
            raise BotError(
                f"Bạn đã có ticket đang mở: {channel.mention if channel else 'hãy kiểm tra danh sách kênh'}."
            )

        # Tìm / tạo danh mục chứa ticket
        category_id = config.get("ticket", {}).get("category_id")
        category = guild.get_channel(category_id) if category_id else None
        if category is None or not isinstance(category, discord.CategoryChannel):
            category = await guild.create_category("🎫 Ticket", reason="Tạo danh mục ticket")
            await self.bot.config_manager.update(guild.id, {"ticket.category_id": category.id})

        staff_role = await self._get_staff_role(guild)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True,
            ),
        }
        if staff_role is not None:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                manage_messages=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True,
            )

        channel_name = f"gopy-{slugify(interaction.user.name)}"
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket góp ý của {interaction.user}",
        )

        embed = self.bot.embeds.info(
            title="💡 Ticket Góp ý",
            description=(
                f"Chào {interaction.user.mention},\n\n"
                "Vui lòng mô tả chi tiết ý kiến đóng góp của bạn ở đây.\n"
                "Đội ngũ staff sẽ phản hồi bạn trong thời gian sớm nhất.\n\n"
                "Nhấn nút **🔒 Đóng ticket** khi bạn muốn kết thúc."
            ),
        )

        from views.tickets import TicketCloseView

        view = TicketCloseView(self.bot)
        welcome = await channel.send(embed=embed, view=view)
        await self.repo.create(channel.id, guild.id, interaction.user.id, "gopy", welcome.id)

        await interaction.response.send_message(
            f"✅ Đã tạo ticket của bạn: {channel.mention}", ephemeral=True
        )

        try:
            await interaction.user.send(
                embed=self.bot.embeds.info(f"Ticket của bạn đã được tạo tại {interaction.guild.name}: {channel.mention}")
            )
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Đóng ticket
    # ------------------------------------------------------------------
    async def close_ticket(self, interaction: discord.Interaction, reason: str) -> None:
        """Đóng ticket: tạo transcript -> gửi kênh log -> xóa kênh."""
        guild = interaction.guild
        if guild is None or not isinstance(interaction.channel, discord.TextChannel):
            raise BotError("Không thể đóng ticket ở đây.")

        ticket = await self.repo.get_by_channel(interaction.channel.id)
        if ticket is None:
            raise BotError("Kênh này không phải là một ticket.")

        staff_role = await self._get_staff_role(guild)
        is_owner = interaction.user.id == ticket["user_id"]
        if not (is_owner or self._is_staff(interaction.user, staff_role)):
            raise BotError("Bạn không có quyền đóng ticket này.")

        await interaction.response.defer()

        # 1. Tạo transcript HTML
        transcript_path = await generate_transcript(self.bot, interaction.channel, ticket, reason)

        # 2. Gửi transcript vào kênh log (hoặc DM người tạo)
        config = await self.bot.config_manager.get(guild.id)
        transcript_channel_id = config.get("ticket", {}).get("transcript_channel_id")
        transcript_channel = guild.get_channel(transcript_channel_id) if transcript_channel_id else None
        if transcript_channel is None:
            mod_log_id = config.get("mod_log_channel")
            transcript_channel = guild.get_channel(mod_log_id) if mod_log_id else None

        transcript_embed = self.bot.embeds.info(
            title="📜 Transcript Ticket",
            description=(
                f"Ticket: **{interaction.channel.name}**\n"
                f"Người tạo: <@{ticket['user_id']}>\n"
                f"Đóng bởi: {interaction.user.mention}\n"
                f"Lý do: {reason or 'Không có lý do'}"
            ),
        )

        sent = False
        if isinstance(transcript_channel, discord.TextChannel):
            try:
                await transcript_channel.send(embed=transcript_embed, file=discord.File(transcript_path))
                sent = True
            except discord.HTTPException as exc:
                logger.warning("Không gửi được transcript vào kênh log: %s", exc)
        if not sent:
            try:
                owner = await self.bot.fetch_user(ticket["user_id"])
                await owner.send(embed=transcript_embed, file=discord.File(transcript_path))
            except discord.HTTPException:
                logger.warning("Không gửi được transcript cho người tạo ticket %s", ticket["user_id"])

        # 3. Dọn file tạm & xóa kênh
        transcript_path.unlink(missing_ok=True)
        await self.repo.close(interaction.channel.id)
        await interaction.channel.delete(reason=f"Đóng ticket bởi {interaction.user}")
