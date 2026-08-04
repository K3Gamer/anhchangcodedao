"""Logging sự kiện server với Embed thống nhất."""

from __future__ import annotations

import discord
from discord.ext import commands


class Logging(commands.Cog):
    """Ghi log toàn bộ sự kiện quan trọng của server."""

    def __init__(self, bot) -> None:
        self.bot = bot

    # ================================================================
    # Hỗ trợ ghi log
    # ================================================================
    async def _log_event(self, guild, event: str, embed: discord.Embed) -> None:
        """Gửi log sự kiện nếu đã cấu hình kênh và sự kiện đang bật."""
        if self.bot.config_manager is None:
            return
        try:
            config = await self.bot.config_manager.get(guild.id)
        except Exception:
            return
        logging_cfg = config.get("logging", {})
        if logging_cfg.get("enabled", True) is False:
            return
        events = logging_cfg.get("events", {})
        if events.get(event, True) is False:
            return
        channel_id = config.get("logging_channel") or config.get("mod_log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # ================================================================
    # Thành viên
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = self.bot.embeds.base(
            title="📥 Thành viên mới",
            description=f"{member.mention} vừa tham gia server.",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`")
        embed.add_field(name="📅 Tạo tài khoản", value=discord.utils.format_dt(member.created_at, "R"))
        embed.add_field(name="👥 Số thành viên", value=str(member.guild.member_count))
        await self._log_event(member.guild, "join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = self.bot.embeds.base(
            title="📤 Thành viên rời",
            description=f"{member} vừa rời khỏi server.",
            color=discord.Color.red(),
        )
        embed.add_field(name="🆔 ID", value=f"`{member.id}`")
        embed.add_field(name="👥 Số thành viên", value=str(member.guild.member_count))
        await self._log_event(member.guild, "leave", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = self.bot.embeds.base(
            title="🔨 Ban",
            description=f"**{user}** đã bị cấm khỏi server.",
            color=discord.Color.red(),
        )
        embed.add_field(name="🆔 ID", value=f"`{user.id}`")
        await self._log_event(guild, "ban", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = self.bot.embeds.base(
            title="🔓 Gỡ ban",
            description=f"**{user}** đã được gỡ cấm.",
            color=discord.Color.green(),
        )
        embed.add_field(name="🆔 ID", value=f"`{user.id}`")
        await self._log_event(guild, "unban", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.guild is None:
            return
        # Đổi biệt danh
        if before.nick != after.nick:
            embed = self.bot.embeds.base(
                title="✏️ Đổi biệt danh",
                description=f"{after.mention}\n**{before.nick or before.name}** → **{after.nick or after.name}**",
            )
            await self._log_event(after.guild, "nickname_update", embed)
        # Thay đổi role
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            parts: list[str] = []
            if added:
                parts.append(f"➕ {', '.join(r.mention for r in added)}")
            if removed:
                parts.append(f"➖ {', '.join(r.mention for r in removed)}")
            embed = self.bot.embeds.base(
                title="🎭 Cập nhật role",
                description=f"{after.mention}\n" + "\n".join(parts),
            )
            await self._log_event(after.guild, "role_update", embed)

    # ================================================================
    # Tin nhắn
    # ================================================================
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        embed = self.bot.embeds.base(
            title="🗑️ Tin nhắn bị xóa",
            description=f"{message.author.mention} trong {message.channel.mention}",
            color=discord.Color.orange(),
        )
        if message.content:
            embed.add_field(name="💬 Nội dung", value=message.content[:1000], inline=False)
        if message.attachments:
            embed.add_field(
                name="📎 File đính kèm",
                value="\n".join(a.filename for a in message.attachments[:5]),
                inline=False,
            )
        embed.add_field(name="🆔 Message ID", value=f"`{message.id}`")
        await self._log_event(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages) -> None:
        first = messages[0] if messages else None
        if first is None or first.guild is None:
            return
        embed = self.bot.embeds.base(
            title="🗑️ Xóa tin nhắn hàng loạt",
            description=f"Đã xóa **{len(messages)}** tin nhắn tại {first.channel.mention}",
            color=discord.Color.orange(),
        )
        await self._log_event(first.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or before.guild is None:
            return
        if before.content == after.content:
            return
        embed = self.bot.embeds.base(
            title="✏️ Tin nhắn đã sửa",
            description=f"{before.author.mention} trong {before.channel.mention}",
        )
        embed.add_field(name="🔹 Trước", value=before.content[:1000] or "*không có*", inline=False)
        embed.add_field(name="🔸 Sau", value=after.content[:1000] or "*không có*", inline=False)
        embed.add_field(name="🔗 Jump", value=f"[Nhảy tới tin nhắn]({after.jump_url})")
        await self._log_event(before.guild, "message_edit", embed)

    # ================================================================
    # Voice
    # ================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if before.channel == after.channel:
            return
        guild = member.guild
        if before.channel is None:
            embed = self.bot.embeds.base(
                title="🎧 Vào voice",
                description=f"{member.mention} vào **{after.channel.name}**",
                color=discord.Color.green(),
            )
        elif after.channel is None:
            embed = self.bot.embeds.base(
                title="🎧 Rời voice",
                description=f"{member.mention} rời **{before.channel.name}**",
                color=discord.Color.red(),
            )
        else:
            embed = self.bot.embeds.base(
                title="🎧 Di chuyển voice",
                description=f"{member.mention} di chuyển từ **{before.channel.name}** → **{after.channel.name}**",
            )
        await self._log_event(guild, "voice", embed)

    # ================================================================
    # Kênh
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel) -> None:
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
            return
        embed = self.bot.embeds.base(
            title="📂 Kênh được tạo",
            description=f"{channel.mention} ({channel.type})",
            color=discord.Color.green(),
        )
        embed.add_field(name="🆔 ID", value=f"`{channel.id}`")
        await self._log_event(channel.guild, "channel", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel) -> None:
        guild = getattr(channel, "guild", None)
        if guild is None:
            return
        embed = self.bot.embeds.base(
            title="🗑️ Kênh bị xóa",
            description=f"**{channel.name}** ({channel.type})",
            color=discord.Color.red(),
        )
        embed.add_field(name="🆔 ID", value=f"`{channel.id}`")
        await self._log_event(guild, "channel", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after) -> None:
        if before.name == after.name:
            return
        embed = self.bot.embeds.base(
            title="✏️ Kênh cập nhật",
            description=f"Kênh {after.mention} đã được đổi tên\n**{before.name}** → **{after.name}**",
        )
        await self._log_event(after.guild, "channel", embed)

    # ================================================================
    # Emoji & Sticker
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after) -> None:
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        if added:
            embed = self.bot.embeds.base(
                title="😀 Emoji được thêm",
                description=" ".join(str(e) for e in added[:10]),
                color=discord.Color.green(),
            )
        elif removed:
            embed = self.bot.embeds.base(
                title="😀 Emoji bị xóa",
                description=", ".join(e.name for e in removed[:10]),
                color=discord.Color.red(),
            )
        else:
            return
        await self._log_event(guild, "emoji", embed)

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after) -> None:
        added = [s for s in after if s not in before]
        removed = [s for s in before if s not in after]
        if added:
            embed = self.bot.embeds.base(
                title="🖼️ Sticker được thêm",
                description=", ".join(s.name for s in added[:10]),
                color=discord.Color.green(),
            )
        elif removed:
            embed = self.bot.embeds.base(
                title="🖼️ Sticker bị xóa",
                description=", ".join(s.name for s in removed[:10]),
                color=discord.Color.red(),
            )
        else:
            return
        await self._log_event(guild, "sticker", embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Logging(bot))
