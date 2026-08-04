"""AntiNuke: giám sát Audit Log, chặn các hành vi phá hoại hàng loạt."""

from __future__ import annotations

import time
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.errors import BotError
from utils.constants import ANTINUKE_FEATURES

# Ánh xạ hành động Audit Log -> tên cấu hình giới hạn
ACTION_MAP: dict[discord.AuditLogAction, str] = {
    discord.AuditLogAction.ban: "bans",
    discord.AuditLogAction.kick: "kicks",
    discord.AuditLogAction.channel_delete: "channel_delete",
    discord.AuditLogAction.channel_create: "channel_create",
    discord.AuditLogAction.role_delete: "role_delete",
    discord.AuditLogAction.role_create: "role_create",
    discord.AuditLogAction.emoji_delete: "emoji_delete",
    discord.AuditLogAction.sticker_delete: "sticker_delete",
    discord.AuditLogAction.webhook_delete: "webhook_delete",
    discord.AuditLogAction.overwrite_update: "permission_edit",
}

_FEATURE_CHOICES = [
    app_commands.Choice(name=feature, value=feature) for feature in ANTINUKE_FEATURES
]
_ACTION_CHOICES = [
    app_commands.Choice(name="Ban", value="ban"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Gỡ quyền", value="strip"),
]


class AntiNuke(commands.Cog):
    """Theo dõi Audit Log theo cửa sổ thời gian, xử lý kẻ phá hoại."""

    def __init__(self, bot) -> None:
        self.bot = bot
        # Trạng thái trong RAM: guild_id -> {feature: [timestamps]}
        self._state: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    # ================================================================
    # Listener
    # ================================================================
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        """Kiểm tra mọi hành động nguy hiểm mới trong Audit Log."""
        guild = entry.guild
        if guild is None:
            return

        config = await self.bot.config_manager.get(guild.id)
        antinuke = config.get("antinuke", {})
        if not antinuke.get("enabled"):
            return

        actor = entry.user
        if actor is None or not isinstance(actor, discord.Member):
            return
        # Luôn miễn trừ chủ server và chính bot
        if actor.id == guild.owner_id or actor.id == self.bot.user.id:
            return
        # Whitelist
        if actor.id in antinuke.get("whitelisted_users", []):
            return
        if any(r.id in antinuke.get("whitelisted_roles", []) for r in actor.roles):
            return

        feature = ACTION_MAP.get(entry.action)
        if feature is None:
            return

        window = antinuke.get("window", 10)
        limit = antinuke.get(f"max_{feature}", 3)
        now = time.time()

        stamps = self._state[guild.id][feature]
        stamps.append(now)
        # Giữ lại các sự kiện trong cửa sổ thời gian
        self._state[guild.id][feature] = [t for t in stamps if now - t <= window]

        if len(self._state[guild.id][feature]) >= limit:
            await self._punish(guild, actor, antinuke, feature)
            self._state[guild.id][feature].clear()

    # ================================================================
    # Xử lý kẻ phá hoại
    # ================================================================
    async def _punish(self, guild, actor, antinuke, feature) -> None:
        action = antinuke.get("action", "ban")
        reason = f"AntiNuke: phát hiện {feature} vượt giới hạn"
        try:
            if action == "ban":
                await guild.ban(actor, reason=reason)
            elif action == "kick":
                await guild.kick(actor, reason=reason)
            elif action == "strip":
                safe_roles = [
                    r for r in actor.roles
                    if not (
                        r.permissions.administrator
                        or r.permissions.manage_guild
                        or r.permissions.manage_roles
                        or r.permissions.manage_channels
                    )
                ]
                await actor.edit(roles=safe_roles, reason=reason)
        except discord.HTTPException as exc:
            self.bot.logger.error("AntiNuke không xử lý được %s: %s", actor, exc)

        embed = self.bot.embeds.base(
            title="🚨 AntiNuke đã kích hoạt",
            description=f"{actor.mention} bị xử lý do hành vi phá hoại.",
            color=discord.Color.red(),
        )
        embed.add_field(name="📌 Hành vi", value=feature, inline=True)
        embed.add_field(name="⚡ Hình phạt", value=action.title(), inline=True)
        await self.bot.send_log(guild, embed)

    # ================================================================
    # Lệnh cấu hình
    # ================================================================
    antinuke = app_commands.Group(
        name="antinuke",
        description="Quản lý hệ thống AntiNuke (Admin)",
        default_permissions=discord.Permissions(administrator=True),
    )

    @antinuke.command(name="toggle", description="Bật/tắt AntiNuke")
    @is_admin()
    async def antinuke_toggle(self, interaction: discord.Interaction, state: bool) -> None:
        await self.bot.config_manager.update(interaction.guild.id, {"antinuke.enabled": state})
        embed = self.bot.embeds.success(f"Đã {'🟢 bật' if state else '🔴 tắt'} **AntiNuke**.")
        await interaction.response.send_message(embed=embed)

    @antinuke.command(name="action", description="Chọn hình phạt khi AntiNuke kích hoạt")
    @is_admin()
    @app_commands.choices(action=_ACTION_CHOICES)
    async def antinuke_action(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        await self.bot.config_manager.update(interaction.guild.id, {"antinuke.action": action})
        label = {"ban": "Ban", "kick": "Kick", "strip": "Gỡ quyền"}[action]
        embed = self.bot.embeds.success(f"Hình phạt AntiNuke = **{label}**.")
        await interaction.response.send_message(embed=embed)

    @antinuke.command(name="limit", description="Cài giới hạn hành vi trong cửa sổ thời gian")
    @is_admin()
    @app_commands.choices(feature=_FEATURE_CHOICES)
    async def antinuke_limit(
        self, interaction: discord.Interaction, feature: str, limit: app_commands.Range[int, 1, 100]
    ) -> None:
        await self.bot.config_manager.update(
            interaction.guild.id, {f"antinuke.max_{feature}": limit}
        )
        embed = self.bot.embeds.success(f"Giới hạn **{feature}** = **{limit}**.")
        await interaction.response.send_message(embed=embed)

    @antinuke.command(name="whitelist", description="Quản lý danh sách được phép của AntiNuke")
    @is_admin()
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Thêm", value="add"),
            app_commands.Choice(name="Gỡ", value="remove"),
        ]
    )
    @app_commands.describe(
        action="Hành động",
        user="Người dùng được phép (chọn 1 trong 2 mục tiêu)",
        role="Role được phép",
    )
    async def antinuke_whitelist(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.User | None = None,
        role: discord.Role | None = None,
    ) -> None:
        targets = [t for t in (user, role) if t is not None]
        if len(targets) != 1:
            raise BotError("Hãy chọn đúng một mục tiêu: user hoặc role.")
        if user is not None:
            field, value, label = "whitelisted_users", user.id, user.mention
        else:
            field, value, label = "whitelisted_roles", role.id, role.mention

        config = await self.bot.config_manager.get(interaction.guild.id)
        current = list(config.get("antinuke", {}).get(field, []))
        if action == "add":
            if value in current:
                raise BotError(f"{label} đã có trong whitelist AntiNuke.")
            current.append(value)
            message = f"Đã thêm {label} vào whitelist AntiNuke."
        else:
            if value not in current:
                raise BotError(f"{label} không có trong whitelist AntiNuke.")
            current.remove(value)
            message = f"Đã gỡ {label} khỏi whitelist AntiNuke."

        await self.bot.config_manager.update(interaction.guild.id, {f"antinuke.{field}": current})
        embed = self.bot.embeds.success(message)
        await interaction.response.send_message(embed=embed)

    @antinuke.command(name="list", description="Xem cấu hình AntiNuke hiện tại")
    @is_admin()
    async def antinuke_list(self, interaction: discord.Interaction) -> None:
        config = await self.bot.config_manager.get(interaction.guild.id)
        an = config.get("antinuke", {})
        embed = self.bot.embeds.base(title="🚨 Cấu hình AntiNuke")
        embed.add_field(name="Tổng thể", value="🟢 Bật" if an.get("enabled") else "🔴 Tắt")
        embed.add_field(name="Hình phạt", value=str(an.get("action", "ban")).title())
        embed.add_field(name="Cửa sổ thời gian", value=f"{an.get('window', 10)} giây")
        for feature in ANTINUKE_FEATURES:
            embed.add_field(name=feature, value=str(an.get(f"max_{feature}", 3)), inline=True)
        embed.add_field(
            name="Whitelist",
            value=f"👤 {len(an.get('whitelisted_users', []))} người • "
                  f"🎭 {len(an.get('whitelisted_roles', []))} role",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(AntiNuke(bot))
