"""Các lệnh chung: ping, chat, help, info, tiện ích."""

from __future__ import annotations

import asyncio
import io
import logging
import platform
import re
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_permissions
from core.errors import BotError
from utils.constants import DEFAULT_PREFIX, FORWARD_DM_USER_ID
from utils.embeds import COLOR_MAP
from utils.time import format_duration, parse_duration
from views.help import CategoryMap, HelpView

logger = logging.getLogger("codi")

POLL_EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]

HELP_CATEGORIES: CategoryMap = {
    "Chung": (
        "ℹ️",
        "Các lệnh thông tin & tiện ích chung.",
        [
            ("/ping", "Kiểm tra bot hoạt động"),
            ("/help", "Hiển thị trợ giúp"),
            ("/uptime", "Thời gian bot hoạt động"),
            ("/invite", "Mời bot về server"),
            ("/avatar", "Xem ảnh đại diện"),
            ("/banner", "Xem banner"),
            ("/userinfo", "Xem thông tin thành viên"),
            ("/serverinfo", "Xem thông tin server"),
            ("/botinfo", "Xem thông tin bot"),
            ("/membercount", "Đếm thành viên"),
            ("/roleinfo", "Xem thông tin role"),
            ("/channelinfo", "Xem thông tin kênh"),
            ("/emojiinfo", "Xem thông tin emoji"),
            ("/poll", "Tạo cuộc bình chọn"),
            ("/embed", "Tạo embed tùy chỉnh"),
            ("/remind", "Đặt lời nhắc riêng"),
            ("!chat", "Echo tin nhắn / file"),
        ],
    ),
    "Leveling": (
        "📊",
        "Tính XP theo hoạt động và bảng xếp hạng.",
        [
            ("/rank", "Xem thẻ cấp độ XP (ảnh)"),
            ("/leaderboard", "Xem bảng xếp hạng XP hình ảnh"),
            ("/rank-reset", "Xóa dữ liệu XP (quản trị)"),
        ],
    ),
    "Quản trị": (
        "🛠️",
        "Các lệnh quản lý server.",
        [
            ("/clear", "Xóa tin nhắn"),
            ("/lock", "Khóa kênh"),
            ("/unlock", "Mở khóa kênh"),
            ("/slowmode", "Cài đặt slowmode"),
            ("/kick", "Kick thành viên"),
            ("/ban", "Ban thành viên"),
            ("/unban", "Gỡ ban"),
            ("/timeout", "Timeout thành viên"),
            ("/untimeout", "Gỡ timeout"),
            ("/move", "Di chuyển 1 thành viên"),
            ("/moveall", "Di chuyển toàn bộ voice"),
            ("/rename", "Đổi biệt danh"),
            ("/role", "Thêm / Gỡ role"),
            ("/announce", "Gửi thông báo"),
            ("!dm", "Gửi tin nhắn riêng cho thành viên"),

        ],
    ),
    "Cảnh cáo": (
        "⚠️",
        "Hệ thống cảnh cáo.",
        [
            ("/warn", "Cảnh cáo thành viên"),
            ("/unwarn", "Gỡ một hoặc toàn bộ cảnh cáo"),
            ("/warnings", "Xem danh sách cảnh cáo"),
        ],
    ),
    "Ticket": (
        "🎫",
        "Hệ thống ticket góp ý.",
        [
            ("/gopyticketsetup", "Cài đặt panel ticket (Admin)"),
            ("/closeticket", "Đóng ticket hiện tại"),
        ],
    ),
    "Bảo mật": (
        "🛡️",
        "AutoMod & AntiNuke.",
        [
            ("/automod toggle", "Bật/tắt tính năng AutoMod"),
            ("/automod action", "Đổi hành động xử lý"),
            ("/automod whitelist", "Quản lý whitelist"),
            ("/automod list", "Xem cấu hình AutoMod"),
            ("/antinuke toggle", "Bật/tắt AntiNuke"),
            ("/antinuke limit", "Cài giới hạn hành vi"),
            ("/antinuke whitelist", "Quản lý whitelist"),
            ("/antinuke list", "Xem cấu hình AntiNuke"),
        ],
    ),
    "Cài đặt": (
        "⚙️",
        "Cấu hình bot cho server.",
        [
            ("/prefix", "Đổi prefix"),
            ("/setmodlog", "Chọn kênh log quản trị"),
            ("/setlogging", "Chọn kênh log sự kiện"),
            ("/settings", "Xem cấu hình server"),
        ],
    ),
}


class General(commands.Cog):
    """Nhóm lệnh chung dành cho mọi thành viên."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self._ready_done = False

    # ================================================================
    # Sự kiện
    # ================================================================
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._ready_done:
            return
        self._ready_done = True
        try:
            app = await self.bot.application_info()
            if app.team is not None:
                self.bot.owner_ids = {m.id for m in app.team.members}
            else:
                self.bot.owner_ids = {app.owner.id}
        except Exception:
            self.bot.owner_ids = set()
        logger.info("Bot sẵn sàng: %s (%s) | %s server", self.bot.user, self.bot.user.id, len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        if self.bot.config_manager is not None:
            await self.bot.config_manager.get(guild.id)  # tạo cấu hình mặc định
        logger.info("Bot tham gia server: %s (%s)", guild.name, guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Forward toàn bộ tin nhắn DM gửi cho bot tới người quản lý."""
        if message.guild is not None or message.author.bot:
            return
        target = self.bot.get_user(FORWARD_DM_USER_ID)
        if target is None:
            try:
                target = await self.bot.fetch_user(FORWARD_DM_USER_ID)
            except discord.HTTPException:
                return
        try:
            files = [await attachment.to_file() for attachment in message.attachments[:10]]
        except discord.HTTPException:
            files = []
        header = f"📩 **{message.author}** (`{message.author.id}`)"
        content = f"{header}:\n{message.content}" if message.content else header
        try:
            await target.send(content=content, files=files)
        except discord.HTTPException:
            pass

    # ================================================================
    # Lệnh prefix
    # ================================================================
    @commands.hybrid_command(name="ping", description="Kiểm tra độ trễ của bot")
    async def ping(self, ctx: commands.Context) -> None:
        """!ping — hiển thị API Ping và Bot Latency."""
        start = time.perf_counter()
        await ctx.typing()
        end = time.perf_counter()
        latency = round(self.bot.latency * 1000, 2)
        roundtrip = round((end - start) * 1000, 2)
        embed = self.bot.embeds.success(
            title="🏓 Pong!",
            description="Bot đang hoạt động bình thường.",
        )
        embed.add_field(name="📶 API Ping", value=f"**{latency} ms**", inline=True)
        embed.add_field(name="⚙️ Bot Latency", value=f"**{roundtrip} ms**", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="chat")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.bot_has_permissions(manage_messages=True)
    async def chat(self, ctx: commands.Context, *, content: str | None = None) -> None:
        """!chat <nội dung> — echo nguyên văn (giữ file & embed) rồi xóa tin nhắn gốc."""
        original = ctx.message
        embeds = [discord.Embed.from_dict(e.to_dict()) for e in original.embeds[:10]]
        files = []
        for attachment in original.attachments[:10]:
            data = await attachment.read()
            files.append(discord.File(io.BytesIO(data), filename=attachment.filename))

        if not content and not embeds and not files:
            embed = self.bot.embeds.error("Vui lòng nhập nội dung hoặc đính kèm file.")
            await ctx.send(embed=embed)
            return

        try:
            await original.delete()
        except discord.HTTPException:
            pass
        await ctx.send(content=content or "", embeds=embeds, files=files)

    # ================================================================
    # Trợ giúp
    # ================================================================
    @commands.hybrid_command(name="help", description="Xem danh sách lệnh của bot")
    async def help(self, ctx: commands.Context) -> None:
        """Xem trợ giúp theo danh mục (Select Menu)."""
        embed = self.bot.embeds.base(
            title="📚 Trợ giúp — Codi",
            description="Chọn một danh mục bên dưới để xem chi tiết các lệnh.",
        )
        view = HelpView(self.bot, HELP_CATEGORIES)
        await ctx.send(embed=embed, view=view)

    # ================================================================
    # Lệnh thông tin
    # ================================================================
    @app_commands.command(name="serverinfo", description="Xem thông tin server")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        bots = sum(m.bot for m in guild.members)
        humans = guild.member_count - bots
        embed = self.bot.embeds.base(title=f"ℹ️ {guild.name}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Không rõ")
        embed.add_field(name="👥 Thành viên", value=f"**{guild.member_count}**")
        embed.add_field(name="🤖 Bot", value=f"**{bots}**")
        embed.add_field(name="👤 Người", value=f"**{humans}**")
        embed.add_field(name="🎭 Roles", value=f"**{len(guild.roles)}**")
        embed.add_field(name="😀 Emoji", value=f"**{len(guild.emojis)}**")
        embed.add_field(name="🚀 Boost", value=f"Level **{guild.premium_tier}** • {guild.premium_subscription_count} boosts")
        embed.add_field(name="🛡️ Verification", value=str(guild.verification_level).title())
        embed.add_field(name="📅 Tạo lúc", value=discord.utils.format_dt(guild.created_at, "R"))
        embed.add_field(name="🆔 ID", value=f"`{guild.id}`")
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Xem thông tin thành viên")
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        badges = [badge for badge in target.public_flags.all()]
        roles = [r.mention for r in target.roles[1:]][:10]
        embed = self.bot.embeds.base(title=f"👤 {target.display_name}")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="🆔 ID", value=f"`{target.id}`")
        embed.add_field(name="📛 Username", value=str(target))
        embed.add_field(name="🤖 Bot?", value="Có" if target.bot else "Không")
        embed.add_field(name="📶 Trạng thái", value=str(target.status).title())
        embed.add_field(name="📅 Tạo tài khoản", value=discord.utils.format_dt(target.created_at, "R"))
        embed.add_field(
            name="🗓️ Tham gia server",
            value=discord.utils.format_dt(target.joined_at, "R") if target.joined_at else "N/A",
        )
        embed.add_field(name="⭐ Top role", value=target.top_role.mention)
        embed.add_field(
            name=f"🎭 Roles ({len(target.roles) - 1})",
            value=" ".join(roles) if roles else "Không có",
            inline=False,
        )
        embed.add_field(
            name="🎖️ Huy hiệu",
            value=", ".join(f"`{b.name}`" for b in badges) if badges else "Không có",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Xem thông tin về bot")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        app = await self.bot.application_info()
        guilds = len(self.bot.guilds)
        users = sum(g.member_count or 0 for g in self.bot.guilds)
        commands_count = len([c for c in self.bot.walk_commands()]) + len(self.bot.tree.get_commands())
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        embed = self.bot.embeds.base(title=f"🤖 {self.bot.user.name}")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="📦 Thư viện", value=f"discord.py **{discord.__version__}**")
        embed.add_field(name="🐍 Python", value=platform.python_version())
        embed.add_field(name="🌐 Server", value=f"**{guilds}** servers")
        embed.add_field(name="👥 Thành viên", value=f"**{users}** users")
        embed.add_field(name="⚙️ Số lệnh", value=f"**{commands_count}**")
        embed.add_field(name="⏱️ Uptime", value=format_duration(uptime.total_seconds()))
        embed.add_field(name="👑 Developer", value=str(app.owner))
        embed.add_field(name="🆔 ID", value=f"`{self.bot.user.id}`")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="membercount", description="Đếm số lượng thành viên")
    async def membercount(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        bots = sum(m.bot for m in guild.members)
        embed = self.bot.embeds.base(title=f"👥 Thành viên {guild.name}")
        embed.add_field(name="📊 Tổng", value=f"**{guild.member_count}**")
        embed.add_field(name="👤 Người", value=f"**{guild.member_count - bots}**")
        embed.add_field(name="🤖 Bot", value=f"**{bots}**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Xem thông tin một role")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role) -> None:
        embed = self.bot.embeds.base(title=f"🎭 Role: {role.name}")
        if role.icon:
            embed.set_thumbnail(url=role.icon.url)
        embed.add_field(name="🆔 ID", value=f"`{role.id}`")
        embed.add_field(name="🎨 Màu", value=str(role.color))
        embed.add_field(name="📌 Vị trí", value=str(role.position))
        embed.add_field(name="👤 Thành viên", value=str(len(role.members)))
        embed.add_field(name="💬 Hoisted", value="Có" if role.hoist else "Không")
        embed.add_field(name="📣 Mentionable", value="Có" if role.mentionable else "Không")
        embed.add_field(name="📅 Tạo lúc", value=discord.utils.format_dt(role.created_at, "R"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="Xem thông tin một kênh")
    async def channelinfo(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | None = None,
    ) -> None:
        target = channel or interaction.channel
        embed = self.bot.embeds.base(title=f"📂 {target.name}")
        embed.add_field(name="🆔 ID", value=f"`{target.id}`")
        embed.add_field(name="📖 Loại", value=str(target.type).title())
        embed.add_field(name="📅 Tạo lúc", value=discord.utils.format_dt(target.created_at, "R"))
        embed.add_field(name="🗂️ Danh mục", value=target.category.name if target.category else "Không có")
        if isinstance(target, discord.TextChannel):
            embed.add_field(name="💬 Topic", value=target.topic or "Không có", inline=False)
            embed.add_field(name="🐢 Slowmode", value=f"{target.slowmode_delay}s")
            embed.add_field(name="🔞 NSFW", value="Có" if target.nsfw else "Không")
            embed.add_field(name="📌 Vị trí", value=str(target.position))
        elif isinstance(target, discord.VoiceChannel):
            embed.add_field(name="🔊 User Limit", value=str(target.user_limit) if target.user_limit else "Không giới hạn")
            embed.add_field(name="👥 Đang kết nối", value=str(len(target.members)))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="emojiinfo", description="Xem thông tin một emoji")
    @app_commands.describe(emoji="Emoji cần xem (vd: <:ten:123456789> hoặc emoji unicode)")
    async def emojiinfo(self, interaction: discord.Interaction, emoji: str) -> None:
        emoji = emoji.strip()
        match = re.match(r"<a?:([a-zA-Z0-9_]+):(\d+)>", emoji)
        if match:
            name = match.group(1)
            emoji_id = int(match.group(2))
            animated = emoji.startswith("<a:")
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}"
            embed = self.bot.embeds.base(title=f"😀 {name}")
            embed.add_field(name="🆔 ID", value=f"`{emoji_id}`")
            embed.add_field(name="🎬 Animated", value="Có" if animated else "Không")
            embed.add_field(name="🔗 Link", value=f"[Nhấn để xem]({url})")
            embed.set_image(url=url)
        else:
            embed = self.bot.embeds.base(title=f"😀 {emoji}")
            embed.add_field(name="🆔 ID", value="`(unicode)`")
            embed.add_field(name="🎬 Animated", value="Không")
            embed.add_field(
                name="📝 Mã Unicode",
                value=", ".join(f"`U+{ord(c):04X}`" for c in emoji) or "Không rõ",
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Xem ảnh đại diện của thành viên")
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        embed = self.bot.embeds.base(title=f"🖼️ Avatar của {target.display_name}")
        embed.set_image(url=target.display_avatar.url)
        view = discord.ui.View(timeout=120)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="📥 Download",
                url=target.display_avatar.url,
            )
        )
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="banner", description="Xem banner của thành viên")
    async def banner(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        user = await self.bot.fetch_user(target.id)
        if user.banner is None:
            embed = self.bot.embeds.error(f"**{target.display_name}** không có banner.")
            await interaction.response.send_message(embed=embed)
            return
        embed = self.bot.embeds.base(title=f"🖼️ Banner của {target.display_name}")
        embed.set_image(url=user.banner.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="Lấy link mời bot")
    async def invite(self, interaction: discord.Interaction) -> None:
        perms = discord.Permissions(administrator=True)
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        embed = self.bot.embeds.info("Nhấn nút bên dưới để mời bot về server của bạn.")
        view = discord.ui.View(timeout=120)
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="🔗 Mời bot", url=url))
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="uptime", description="Xem thời gian bot đã hoạt động")
    async def uptime(self, interaction: discord.Interaction) -> None:
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        embed = self.bot.embeds.success(
            description=f"Bot đã hoạt động được **{format_duration(uptime.total_seconds())}**."
        )
        embed.add_field(name="🕒 Bắt đầu lúc", value=discord.utils.format_dt(self.bot.start_time, "F"))
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # Tiện ích
    # ================================================================
    @app_commands.command(name="poll", description="Tạo cuộc bình chọn")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    @app_commands.describe(
        question="Câu hỏi bình chọn",
        option_1="Lựa chọn 1",
        option_2="Lựa chọn 2",
        option_3="Lựa chọn 3 (tùy chọn)",
        option_4="Lựa chọn 4 (tùy chọn)",
        option_5="Lựa chọn 5 (tùy chọn)",
        option_6="Lựa chọn 6 (tùy chọn)",
        option_7="Lựa chọn 7 (tùy chọn)",
        option_8="Lựa chọn 8 (tùy chọn)",
        option_9="Lựa chọn 9 (tùy chọn)",
        option_10="Lựa chọn 10 (tùy chọn)",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option_1: str,
        option_2: str,
        option_3: str | None = None,
        option_4: str | None = None,
        option_5: str | None = None,
        option_6: str | None = None,
        option_7: str | None = None,
        option_8: str | None = None,
        option_9: str | None = None,
        option_10: str | None = None,
    ) -> None:
        options = [o for o in (option_1, option_2, option_3, option_4, option_5, option_6, option_7, option_8, option_9, option_10) if o]
        if len(options) > 10:
            options = options[:10]
        description = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options))
        embed = self.bot.embeds.base(title=f"📊 {question}", description=description)
        embed.set_footer(
            text=f"Được tạo bởi {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        for emoji in POLL_EMOJIS[: len(options)]:
            await message.add_reaction(emoji)

    @app_commands.command(name="embed", description="Tạo embed tùy chỉnh")
    @require_permissions("manage_messages")
    @app_commands.describe(
        title="Tiêu đề embed",
        description="Nội dung embed",
        color="Màu sắc (blurple, red, green, orange, white)",
        footer="Footer (tùy chọn)",
        thumbnail="Link ảnh thumbnail (tùy chọn)",
        image="Link ảnh lớn (tùy chọn)",
        channel="Kênh gửi embed (mặc định kênh hiện tại)",
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: str = "blurple",
        footer: str | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        color_choice = COLOR_MAP.get(color.lower(), COLOR_MAP["blurple"])
        embed = self.bot.embeds.base(title=title, description=description, color=color_choice)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        if footer:
            embed.set_footer(text=footer)
        target = channel or interaction.channel
        if target is None:
            raise BotError("Kênh không hợp lệ.")
        await target.send(embed=embed)
        await interaction.response.send_message(
            embed=self.bot.embeds.success(f"Embed đã được gửi tới {target.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="remind", description="Đặt lời nhắc gửi qua tin nhắn riêng")
    @app_commands.describe(
        duration="Thời gian (vd: 10m, 1h30m, 2d)",
        message="Nội dung nhắc nhở",
    )
    async def remind(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            raise BotError("Định dạng thời gian không hợp lệ. VD: `10m`, `1h30m`, `2d`")
        if seconds < 10:
            raise BotError("Thời gian nhắc nhở tối thiểu là 10 giây.")
        if seconds > 30 * 86400:
            raise BotError("Thời gian nhắc nhở tối đa là 30 ngày.")
        embed = self.bot.embeds.success(f"⏰ Đã đặt lời nhắc sau **{format_duration(seconds)}**.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.bot.loop.create_task(self._send_reminder(interaction.user, seconds, message))

    async def _send_reminder(
        self, user: discord.User, seconds: int, message: str
    ) -> None:
        """Gửi DM sau khi hết thời gian đặt trước."""
        await asyncio.sleep(seconds)
        try:
            embed = self.bot.embeds.info(f"⏰ **Nhắc nhở của bạn:**\n{message}")
            await user.send(embed=embed)
        except discord.HTTPException:
            pass


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(General(bot))
