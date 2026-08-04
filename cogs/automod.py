"""AutoMod: chống spam, mention, link, invite, scam, emoji, caps, từ cấm, flood, slowmode tự động."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from database.warns import WarnRepository
from utils.constants import (
    ACTION_SEVERITY,
    AUTOMOD_ACTIONS,
    AUTOMOD_FEATURES,
    BAD_WORDS,
    EMOJI_REGEX,
    INVITE_REGEX,
    SCAM_KEYWORDS,
    SCAM_URL_KEYWORDS,
    URL_REGEX,
)

# Danh sách lựa chọn cho slash command
_FEATURE_CHOICES = [
    app_commands.Choice(name=feature, value=feature) for feature in AUTOMOD_FEATURES
]
_ACTION_CHOICES = [
    app_commands.Choice(name=action.title(), value=action) for action in AUTOMOD_ACTIONS
]


class AutoMod(commands.Cog):
    """Giám sát tin nhắn theo cấu hình và xử lý vi phạm."""

    def __init__(self, bot) -> None:
        self.bot = bot
        # Bộ đếm trong RAM để tránh truy vấn MongoDB cho mỗi tin nhắn
        self._spam: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=30))
        self._flood: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(lambda: deque(maxlen=30))
        self._channel_msgs: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=50))
        self._slowmode_tasks: dict[int, asyncio.Task] = {}

    # ================================================================
    # Listener chính
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Kiểm tra mọi tin nhắn (không phải lệnh) trước khi vào server."""
        if message.author.bot:
            return
        if message.guild is None or message.guild.me is None:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not message.guild.me.guild_permissions.manage_messages:
            return

        config = await self.bot.config_manager.get(message.guild.id)
        automod = config.get("automod", {})
        if not automod.get("enabled"):
            return

        # Bỏ qua tin nhắn là lệnh / mention bot
        prefix = config.get("prefix") or "!"
        if message.content.startswith(prefix) or self.bot.user in message.mentions:
            return

        # Bỏ qua các đối tượng trong whitelist
        if message.author.id in automod.get("whitelisted_users", []):
            return
        if message.channel.id in automod.get("whitelisted_channels", []):
            return
        if any(r.id in automod.get("whitelisted_roles", []) for r in message.author.roles):
            return
        if message.author.guild_permissions.manage_messages:
            return

        violations = await self._check_message(message, automod)
        if violations:
            await self._handle_violations(message, automod, violations)
        else:
            await self._auto_slowmode(message, automod)

    # ================================================================
    # Kiểm tra tin nhắn
    # ================================================================
    async def _check_message(
        self, message: discord.Message, automod: dict
    ) -> list[tuple[str, str]]:
        """Chạy các luật AutoMod, trả về danh sách (tên tính năng, hành động)."""
        content = message.content or ""
        lower = content.lower()
        violations: list[tuple[str, str]] = []

        # Anti Spam: quá nhiều tin trong khoảng thời gian ngắn
        spam_cfg = automod.get("anti_spam", {})
        if spam_cfg.get("enabled"):
            key = (message.guild.id, message.author.id)
            now = time.monotonic()
            self._spam[key].append(now)
            recent = sum(1 for t in self._spam[key] if now - t <= spam_cfg.get("interval", 8))
            if recent > spam_cfg.get("max_messages", 6):
                violations.append(("anti_spam", spam_cfg.get("action", "delete")))

        # Anti Flood: gửi lặp nội dung giống nhau
        flood_cfg = automod.get("anti_flood", {})
        if flood_cfg.get("enabled"):
            key = (message.guild.id, message.author.id)
            now = time.monotonic()
            normalized = " ".join(lower.split())
            self._flood[key].append((now, normalized))
            recent = sum(
                1 for t, text in self._flood[key]
                if now - t <= flood_cfg.get("interval", 20) and text == normalized
            )
            if recent > flood_cfg.get("max_duplicates", 4):
                violations.append(("anti_flood", flood_cfg.get("action", "delete")))

        # Anti Mention: quá nhiều mention trong một tin
        mention_cfg = automod.get("anti_mention", {})
        if mention_cfg.get("enabled"):
            if len(message.mentions) > mention_cfg.get("max_mentions", 6):
                violations.append(("anti_mention", mention_cfg.get("action", "delete")))

        # Anti Link: chứa URL
        link_cfg = automod.get("anti_link", {})
        if link_cfg.get("enabled"):
            if content and URL_REGEX.search(content):
                violations.append(("anti_link", link_cfg.get("action", "delete")))

        # Anti Invite: chứa lời mời Discord
        invite_cfg = automod.get("anti_invite", {})
        if invite_cfg.get("enabled"):
            if content and INVITE_REGEX.search(content):
                violations.append(("anti_invite", invite_cfg.get("action", "delete")))

        # Anti Scam: từ khóa scam / link scam
        scam_cfg = automod.get("anti_scam", {})
        if scam_cfg.get("enabled"):
            if any(kw in lower for kw in SCAM_KEYWORDS) or any(kw in lower for kw in SCAM_URL_KEYWORDS):
                violations.append(("anti_scam", scam_cfg.get("action", "delete")))

        # Anti Emoji: quá nhiều emoji
        emoji_cfg = automod.get("anti_emoji", {})
        if emoji_cfg.get("enabled"):
            if len(EMOJI_REGEX.findall(content)) > emoji_cfg.get("max_emojis", 15):
                violations.append(("anti_emoji", emoji_cfg.get("action", "delete")))

        # Anti Caps: quá nhiều chữ hoa
        caps_cfg = automod.get("anti_caps", {})
        if caps_cfg.get("enabled"):
            letters = [c for c in content if c.isalpha()]
            if len(content) >= caps_cfg.get("min_chars", 8) and letters:
                uppercase = sum(1 for c in letters if c.isupper())
                if uppercase / len(letters) >= caps_cfg.get("max_percent", 0.7):
                    violations.append(("anti_caps", caps_cfg.get("action", "delete")))

        # Anti Bad Words: chứa từ cấm
        badword_cfg = automod.get("anti_badwords", {})
        if badword_cfg.get("enabled"):
            if any(bad in lower for bad in BAD_WORDS):
                violations.append(("anti_badwords", badword_cfg.get("action", "delete")))

        return violations

    # ================================================================
    # Xử lý vi phạm
    # ================================================================
    async def _handle_violations(self, message, automod, violations) -> None:
        """Áp dụng hành động nghiêm trọng nhất và ghi log."""
        best = max(violations, key=lambda v: ACTION_SEVERITY.get(v[1], 0))
        action = best[1]
        features = ", ".join(dict.fromkeys(v[0] for v in violations))
        member = message.author
        guild = message.guild
        reason = f"AutoMod: {features}"

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        if action in ("warn", "timeout", "kick", "ban"):
            if action == "warn":
                repo = WarnRepository(self.bot.db)
                await repo.add(guild.id, member.id, self.bot.user.id, reason)
            elif action == "timeout":
                try:
                    until = discord.utils.utcnow() + timedelta(minutes=10)
                    await member.timeout(until=until, reason=reason)
                except discord.HTTPException:
                    pass
            elif action == "kick":
                try:
                    await member.kick(reason=reason)
                except discord.HTTPException:
                    pass
            elif action == "ban":
                try:
                    await guild.ban(member, reason=reason)
                except discord.HTTPException:
                    pass

        embed = self.bot.embeds.base(
            title="🛡️ AutoMod",
            description=f"{member.mention} đã bị xử lý do vi phạm.",
        )
        embed.add_field(name="📌 Vi phạm", value=features, inline=True)
        embed.add_field(name="⚡ Hành động", value=action.title(), inline=True)
        embed.add_field(name="📂 Kênh", value=message.channel.mention, inline=False)
        if message.content:
            embed.add_field(name="💬 Nội dung", value=message.content[:1000], inline=False)
        await self.bot.send_log(guild, embed)

    # ================================================================
    # Auto Slowmode
    # ================================================================
    async def _auto_slowmode(self, message, automod) -> None:
        cfg = automod.get("auto_slowmode", {})
        if not cfg.get("enabled"):
            return
        if message.channel.slowmode_delay > 0:
            return

        now = time.monotonic()
        stamps = self._channel_msgs[message.channel.id]
        stamps.append(now)
        window = cfg.get("window", 10)
        count = sum(1 for t in stamps if now - t <= window)

        if count >= cfg.get("threshold", 8):
            seconds = cfg.get("slowmode_seconds", 10)
            try:
                await message.channel.edit(slowmode_delay=seconds, reason="Auto slowmode kích hoạt")
            except discord.HTTPException:
                return
            task = self.bot.loop.create_task(self._reset_slowmode(message.channel.id, seconds))
            self._slowmode_tasks[message.channel.id] = task

    async def _reset_slowmode(self, channel_id: int, duration: int) -> None:
        """Tắt slowmode sau khi hết thời gian nếu không bị kích hoạt lại."""
        await asyncio.sleep(duration)
        if self._slowmode_tasks.pop(channel_id, None) is None:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.edit(slowmode_delay=0, reason="Auto slowmode hết hạn")
        except discord.HTTPException:
            pass

    # ================================================================
    # Lệnh cấu hình
    # ================================================================
    automod = app_commands.Group(
        name="automod",
        description="Quản lý AutoMod (Admin)",
        default_permissions=discord.Permissions(administrator=True),
    )

    @automod.command(name="toggle", description="Bật/tắt một tính năng AutoMod")
    @is_admin()
    @app_commands.choices(feature=_FEATURE_CHOICES)
    async def automod_toggle(
        self, interaction: discord.Interaction, feature: str, state: bool
    ) -> None:
        await self.bot.config_manager.update(
            interaction.guild.id, {f"automod.{feature}.enabled": state}
        )
        embed = self.bot.embeds.success(
            f"Đã {'🟢 bật' if state else '🔴 tắt'} **{feature}**."
        )
        await interaction.response.send_message(embed=embed)

    @automod.command(name="action", description="Đặt hành động xử lý vi phạm cho một tính năng")
    @is_admin()
    @app_commands.choices(feature=_FEATURE_CHOICES, action=_ACTION_CHOICES)
    async def automod_action(
        self, interaction: discord.Interaction, feature: str, action: str
    ) -> None:
        if feature == "auto_slowmode":
            raise BotError("auto_slowmode không dùng hành động xử lý.")
        await self.bot.config_manager.update(
            interaction.guild.id, {f"automod.{feature}.action": action}
        )
        embed = self.bot.embeds.success(
            f"Hành động xử lý **{feature}** = `{action}`."
        )
        await interaction.response.send_message(embed=embed)

    @automod.command(name="whitelist", description="Quản lý danh sách được phép của AutoMod")
    @is_admin()
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Thêm", value="add"),
            app_commands.Choice(name="Gỡ", value="remove"),
        ]
    )
    @app_commands.describe(
        action="Hành động",
        channel="Kênh được phép (chọn 1 trong 3 mục tiêu)",
        user="Người dùng được phép",
        role="Role được phép",
    )
    async def automod_whitelist(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: discord.TextChannel | None = None,
        user: discord.User | None = None,
        role: discord.Role | None = None,
    ) -> None:
        targets = [t for t in (channel, user, role) if t is not None]
        if len(targets) != 1:
            raise BotError("Hãy chọn đúng một mục tiêu: channel, user hoặc role.")
        if channel is not None:
            field, value, label = "whitelisted_channels", channel.id, channel.mention
        elif user is not None:
            field, value, label = "whitelisted_users", user.id, user.mention
        else:
            field, value, label = "whitelisted_roles", role.id, role.mention

        config = await self.bot.config_manager.get(interaction.guild.id)
        current = list(config.get("automod", {}).get(field, []))
        if action == "add":
            if value in current:
                raise BotError(f"{label} đã có trong whitelist AutoMod.")
            current.append(value)
            message = f"Đã thêm {label} vào whitelist AutoMod."
        else:
            if value not in current:
                raise BotError(f"{label} không có trong whitelist AutoMod.")
            current.remove(value)
            message = f"Đã gỡ {label} khỏi whitelist AutoMod."

        await self.bot.config_manager.update(interaction.guild.id, {f"automod.{field}": current})
        embed = self.bot.embeds.success(message)
        await interaction.response.send_message(embed=embed)

    @automod.command(name="list", description="Xem cấu hình AutoMod hiện tại")
    @is_admin()
    async def automod_list(self, interaction: discord.Interaction) -> None:
        config = await self.bot.config_manager.get(interaction.guild.id)
        automod = config.get("automod", {})
        embed = self.bot.embeds.base(title="🛡️ Cấu hình AutoMod")
        embed.add_field(
            name="Tổng thể",
            value="🟢 Bật" if automod.get("enabled") else "🔴 Tắt",
            inline=False,
        )
        for feature in AUTOMOD_FEATURES:
            cfg = automod.get(feature, {})
            state = "🟢" if cfg.get("enabled") else "🔴"
            detail = f"{state} **{feature}**"
            if cfg.get("enabled") and feature != "auto_slowmode":
                detail += f" → `{cfg.get('action', 'delete')}`"
            embed.add_field(name=feature, value=detail, inline=True)
        embed.add_field(
            name="Whitelist",
            value=(
                f"📺 {len(automod.get('whitelisted_channels', []))} kênh • "
                f"👤 {len(automod.get('whitelisted_users', []))} người • "
                f"🎭 {len(automod.get('whitelisted_roles', []))} role"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(AutoMod(bot))
