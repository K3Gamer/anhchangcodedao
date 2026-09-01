"""Các lệnh quản trị server: clear, lock, ban, kick, timeout, move, role..."""

from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_permissions, require_prefix_permissions
from core.errors import BotError
from utils.time import format_duration, parse_duration
from views.confirm import ConfirmView


class Moderation(commands.Cog):
    """Nhóm lệnh quản trị dành cho Mod/Admin."""

    def __init__(self, bot) -> None:
        self.bot = bot

    async def _log_mod_action(self, guild: discord.Guild, embed: discord.Embed) -> None:
        await self.bot.send_log(guild, embed)

    # ================================================================
    # clear
    # ================================================================
    @app_commands.command(name="clear", description="Xóa tin nhắn trong kênh")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    @app_commands.describe(amount="Số tin nhắn cần xóa (1-1000, mặc định 100)")
    @require_permissions("manage_messages")
    async def clear(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000] = 100
    ) -> None:
        if interaction.channel is None:
            raise BotError("Không thể thực hiện ở đây.")
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(
            limit=amount, bulk=True, reason=f"Clear bởi {interaction.user}"
        )
        embed = self.bot.embeds.success(f"Đã xóa **{len(deleted)}** tin nhắn.")
        await interaction.followup.send(embed=embed, ephemeral=True)
        log_embed = self.bot.embeds.base(
            title="🧹 Clear",
            description=f"{interaction.user.mention} đã xóa **{len(deleted)}** tin nhắn tại {interaction.channel.mention}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # lock / unlock
    # ================================================================
    async def _lock_unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        lock: bool,
        reason: str | None,
    ) -> None:
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = not lock
        overwrite.send_messages_in_threads = not lock
        overwrite.create_public_threads = not lock
        overwrite.create_private_threads = not lock
        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=reason or f"{'Lock' if lock else 'Unlock'} bởi {interaction.user}",
        )
        action_text = "🔒 Đã khóa" if lock else "🔓 Đã mở khóa"
        embed = self.bot.embeds.success(f"{action_text} kênh {channel.mention}.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title=action_text,
            description=f"{interaction.user.mention} đã thao tác với {channel.mention}\nLý do: {reason or 'Không có'}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    @app_commands.command(name="lock", description="Khóa kênh (chặn gửi tin nhắn)")
    @app_commands.describe(channel="Kênh cần khóa", reason="Lý do khóa")
    @require_permissions("manage_channels")
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: str | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            raise BotError("Chỉ áp dụng được với kênh văn bản.")
        await self._lock_unlock(interaction, target, lock=True, reason=reason)

    @app_commands.command(name="unlock", description="Mở khóa kênh")
    @app_commands.describe(channel="Kênh cần mở khóa", reason="Lý do mở khóa")
    @require_permissions("manage_channels")
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: str | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            raise BotError("Chỉ áp dụng được với kênh văn bản.")
        await self._lock_unlock(interaction, target, lock=False, reason=reason)

    # ================================================================
    # slowmode
    # ================================================================
    @app_commands.command(name="slowmode", description="Cài đặt slowmode cho kênh")
    @app_commands.describe(duration="Thời gian slowmode (vd: 0, 5s, 10m, 1h)", channel="Kênh cần cài")
    @require_permissions("manage_channels")
    async def slowmode(
        self,
        interaction: discord.Interaction,
        duration: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            raise BotError("Chỉ áp dụng được với kênh văn bản.")
        seconds = parse_duration(duration)
        if seconds is None:
            raise BotError("Định dạng thời gian không hợp lệ. VD: `0`, `5s`, `10m`, `1h`")
        if seconds > 21600:
            raise BotError("Slowmode tối đa là 6 giờ.")
        await target.edit(slowmode_delay=seconds, reason=f"Slowmode bởi {interaction.user}")
        text = "đã tắt" if seconds == 0 else f"**{format_duration(seconds)}**"
        embed = self.bot.embeds.success(f"🐢 Đã cài slowmode {target.mention} là {text}.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="🐢 Slowmode",
            description=f"{interaction.user.mention} đặt slowmode {target.mention} = {text}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # kick / ban / unban
    # ================================================================
    @app_commands.command(name="kick", description="Kick thành viên khỏi server")
    @app_commands.describe(member="Thành viên cần kick", reason="Lý do kick")
    @require_permissions("kick_members")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        if member.id == interaction.user.id:
            raise BotError("Bạn không thể kick chính mình.")
        if member.top_role >= interaction.guild.me.top_role:
            raise BotError("Không thể kick thành viên có role cao hơn hoặc ngang bot.")
        reason = reason or "Không có lý do"
        await member.kick(reason=f"{reason} | Bởi {interaction.user}")
        embed = self.bot.embeds.success(f"👢 Đã kick **{member}**.\nLý do: {reason}")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="👢 Kick",
            description=f"{interaction.user.mention} đã kick {member.mention}\nLý do: {reason}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    @app_commands.command(name="ban", description="Ban thành viên khỏi server")
    @app_commands.describe(
        member="Người dùng cần ban",
        reason="Lý do ban",
        delete_days="Xóa tin nhắn của người bị ban trong bao nhiêu ngày (0-7)",
    )
    @require_permissions("ban_members")
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.User,
        reason: str | None = None,
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        reason = reason or "Không có lý do"
        kwargs: dict = {"reason": f"{reason} | Bởi {interaction.user}"}
        if delete_days:
            kwargs["delete_message_seconds"] = delete_days * 86400
        await interaction.guild.ban(member, **kwargs)
        embed = self.bot.embeds.success(f"🔨 Đã ban **{member}**.\nLý do: {reason}")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="🔨 Ban",
            description=f"{interaction.user.mention} đã ban {member.mention}\nLý do: {reason}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    @app_commands.command(name="unban", description="Gỡ cấm một người dùng")
    @app_commands.describe(user_id="ID người dùng cần gỡ ban", reason="Lý do gỡ ban")
    @require_permissions("ban_members")
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str | None = None,
    ) -> None:
        try:
            user = await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            raise BotError("ID người dùng không hợp lệ.")
        reason = reason or "Không có lý do"
        await interaction.guild.unban(user, reason=f"{reason} | Bởi {interaction.user}")
        embed = self.bot.embeds.success(f"🔓 Đã gỡ ban **{user}**.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="🔓 Unban",
            description=f"{interaction.user.mention} đã gỡ ban {user.mention}\nLý do: {reason}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # timeout / untimeout
    # ================================================================
    @app_commands.command(name="timeout", description="Timeout (cấm chat tạm thời) thành viên")
    @app_commands.describe(
        member="Thành viên cần timeout",
        duration="Thời gian timeout (vd: 10m, 2h, 1d — tối đa 28 ngày)",
        reason="Lý do timeout",
    )
    @require_permissions("moderate_members")
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str | None = None,
    ) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            raise BotError("Định dạng thời gian không hợp lệ. VD: `10m`, `2h`, `1d`")
        if seconds > 28 * 86400:
            raise BotError("Thời gian timeout tối đa là 28 ngày.")
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        reason = reason or "Không có lý do"
        await member.timeout(until=until, reason=f"{reason} | Bởi {interaction.user}")
        embed = self.bot.embeds.success(
            f"⏳ Đã timeout **{member.display_name}** trong **{format_duration(seconds)}**.\nLý do: {reason}"
        )
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="⏳ Timeout",
            description=f"{interaction.user.mention} đã timeout {member.mention}\nThời gian: {format_duration(seconds)}\nLý do: {reason}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    @app_commands.command(name="untimeout", description="Gỡ timeout cho thành viên")
    @app_commands.describe(member="Thành viên cần gỡ timeout", reason="Lý do gỡ")
    @require_permissions("moderate_members")
    async def untimeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        reason = reason or "Không có lý do"
        await member.timeout(until=None, reason=f"{reason} | Bởi {interaction.user}")
        embed = self.bot.embeds.success(f"✅ Đã gỡ timeout cho **{member.display_name}**.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="✅ Gỡ timeout",
            description=f"{interaction.user.mention} đã gỡ timeout cho {member.mention}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # move / moveall
    # ================================================================
    @app_commands.command(name="move", description="Di chuyển thành viên sang voice channel khác")
    @app_commands.describe(member="Thành viên cần di chuyển", channel="Voice channel đích")
    @require_permissions("move_members")
    async def move(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        channel: discord.VoiceChannel,
    ) -> None:
        if member.voice is None or member.voice.channel is None:
            raise BotError(f"**{member.display_name}** không ở trong voice channel.")
        await member.move_to(channel, reason=f"Move bởi {interaction.user}")
        embed = self.bot.embeds.success(f"🎧 Đã di chuyển **{member.display_name}** tới {channel.mention}.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="🎧 Move",
            description=f"{interaction.user.mention} đã di chuyển {member.mention} tới {channel.mention}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    @app_commands.command(name="moveall", description="Di chuyển toàn bộ thành viên giữa 2 voice channel")
    @app_commands.describe(from_channel="Voice channel nguồn", to_channel="Voice channel đích")
    @require_permissions("move_members")
    async def moveall(
        self,
        interaction: discord.Interaction,
        from_channel: discord.VoiceChannel,
        to_channel: discord.VoiceChannel,
    ) -> None:
        members = list(from_channel.members)
        if not members:
            raise BotError(f"Không có thành viên nào trong **{from_channel.name}**.")
        if from_channel.id == to_channel.id:
            raise BotError("Hai kênh phải khác nhau.")

        async def on_confirm(confirm_interaction: discord.Interaction) -> None:
            moved = 0
            for member in members:
                try:
                    await member.move_to(to_channel, reason=f"Moveall bởi {confirm_interaction.user}")
                    moved += 1
                except discord.HTTPException:
                    continue
            embed = self.bot.embeds.success(
                f"Đã di chuyển **{moved}/{len(members)}** thành viên tới {to_channel.mention}."
            )
            try:
                await confirm_interaction.response.edit_message(embed=embed, view=None)
            except discord.HTTPException:
                pass
            await confirm_interaction.followup.send(embed=embed, ephemeral=True)

        embed = self.bot.embeds.warning(
            f"Bạn có chắc muốn di chuyển **{len(members)}** thành viên\n"
            f"từ **{from_channel.name}** → **{to_channel.name}**?"
        )
        view = ConfirmView(on_confirm=on_confirm, confirm_label="Di chuyển")
        view.bind(interaction)
        await interaction.response.send_message(embed=embed, view=view)

    # ================================================================
    # rename
    # ================================================================
    @app_commands.command(name="rename", description="Đổi biệt danh (nickname) cho thành viên")
    @app_commands.describe(member="Thành viên cần đổi", nickname="Biệt danh mới (bỏ trống để reset)")
    @require_permissions("manage_nicknames")
    async def rename(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        nickname: str | None = None,
    ) -> None:
        old = member.display_name
        await member.edit(nick=nickname, reason=f"Rename bởi {interaction.user}")
        new = nickname or "username gốc"
        embed = self.bot.embeds.success(f"Đã đổi nickname **{old}** → **{new}**.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="✏️ Rename",
            description=f"{interaction.user.mention} đổi nickname {member.mention}\n**{old}** → **{new}**",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # role
    # ================================================================
    @app_commands.command(name="role", description="Thêm hoặc gỡ role cho thành viên")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Thêm (Add)", value="add"),
            app_commands.Choice(name="Gỡ (Remove)", value="remove"),
        ]
    )
    @app_commands.describe(action="Hành động", member="Thành viên", role="Role cần thao tác")
    @require_permissions("manage_roles")
    async def role(
        self,
        interaction: discord.Interaction,
        action: str,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        if role >= interaction.guild.me.top_role:
            raise BotError("Bot không thể thao tác role này (role cao hơn hoặc ngang bot).")
        if action == "add":
            if role in member.roles:
                raise BotError(f"**{member.display_name}** đã có role {role.mention}.")
            await member.add_roles(role, reason=f"Role add bởi {interaction.user}")
            embed = self.bot.embeds.success(f"Đã thêm role {role.mention} cho **{member.display_name}**.")
        else:
            if role not in member.roles:
                raise BotError(f"**{member.display_name}** không có role {role.mention}.")
            await member.remove_roles(role, reason=f"Role remove bởi {interaction.user}")
            embed = self.bot.embeds.success(f"Đã gỡ role {role.mention} khỏi **{member.display_name}**.")
        await interaction.response.send_message(embed=embed)
        log_embed = self.bot.embeds.base(
            title="🎭 Role update",
            description=f"{interaction.user.mention} đã {'thêm' if action == 'add' else 'gỡ'} {role.mention} "
                        f"cho {member.mention}",
        )
        await self._log_mod_action(interaction.guild, log_embed)

    # ================================================================
    # dm
    # ================================================================
    @commands.command(name="dm", description="Gửi tin nhắn riêng cho thành viên")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @require_prefix_permissions("moderate_members")
    async def dm(
        self,
        ctx: commands.Context,
        user: discord.Member,
        *,
        message: str,
    ) -> None:
        """!dm <thành viên> <nội dung> — gửi tin nhắn riêng cho thành viên."""
        if user.id == ctx.author.id:
            raise BotError("Bạn không thể gửi DM cho chính mình.")
        if user.bot:
            raise BotError("Không thể gửi DM cho bot.")
        try:
            await user.send(message)
        except discord.Forbidden:
            raise BotError(f"Không thể gửi DM cho **{user}** — có thể họ đã tắt nhận tin nhắn riêng.")
        except discord.HTTPException:
            raise BotError(f"Gửi DM cho **{user}** thất bại, vui lòng thử lại sau.")
        await ctx.message.delete()
        log_embed = self.bot.embeds.base(
            title="📩 DM",
            description=f"{ctx.author.mention} đã gửi DM cho {user.mention}\nNội dung: {message}",
        )
        await self._log_mod_action(ctx.guild, log_embed)

    # ================================================================
    # announce
    # ================================================================
    @app_commands.command(name="announce", description="Gửi thông báo vào một kênh")
    @app_commands.describe(
        channel="Kênh nhận thông báo",
        title="Tiêu đề thông báo",
        message="Nội dung thông báo",
        role="Role được nhắc (ping) kèm theo (tùy chọn)",
    )
    @require_permissions("manage_guild")
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        message: str,
        role: discord.Role | None = None,
    ) -> None:
        embed = self.bot.embeds.base(title=title, description=message)
        content = role.mention if role else None
        await channel.send(content=content, embed=embed)
        await interaction.response.send_message(
            embed=self.bot.embeds.success(f"Đã gửi thông báo tới {channel.mention}."),
            ephemeral=True,
        )
        log_embed = self.bot.embeds.base(
            title="📢 Announce",
            description=f"{interaction.user.mention} đã gửi thông báo tới {channel.mention}",
        )
        await self._log_mod_action(interaction.guild, log_embed)


async def setup(bot) -> None:
    """Hàm setup chuẩn của discord.py để nạp cog."""
    await bot.add_cog(Moderation(bot))
