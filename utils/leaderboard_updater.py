"""Tự động cập nhật leaderboard trong kênh đã cấu hình.

Chế độ mặc định: cập nhật ngay khi XP thay đổi.
Khi XP thay đổi liên tục (nhiều lần trong 30s): chuyển sang chế độ debounce 30s.
Khi hết thay đổi liên tục: chuyển lại chế độ cập nhật ngay.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from core.bot import CodiBot

logger = logging.getLogger("codi")

DEBOUNCE_THRESHOLD = 30.0  # giây — nếu có thay đổi trong khoảng này thì debounce
TOP_LIMIT = 10  # số người hiển thị trên leaderboard


class LeaderboardUpdater:
    """Theo dõi thay đổi XP và tự động cập nhật ảnh leaderboard."""

    def __init__(self, bot: CodiBot) -> None:
        self.bot = bot
        self._pending: dict[int, float] = {}  # guild_id -> timestamp lần thay đổi gần nhất
        self._last_update: dict[int, float] = {}  # guild_id -> timestamp cập nhật cuối
        self._locks: dict[int, asyncio.Lock] = {}
        self._task: asyncio.Task[None] | None = None

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    # ------------------------------------------------------------------
    # Khởi động / dừng background task
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Gọi từ on_message khi XP thực sự thay đổi
    # ------------------------------------------------------------------
    async def notify_xp_change(self, guild_id: int) -> None:
        now = time.monotonic()
        self._pending[guild_id] = now

        last = self._last_update.get(guild_id, 0.0)
        elapsed = now - last

        # Nếu chưa từng cập nhật hoặc đã qua DEBOUNCE_THRESHOLD -> cập nhật ngay
        if elapsed >= DEBOUNCE_THRESHOLD:
            await self._do_update(guild_id)
        # Nếu không thì chờ background task xử lý (debounce)

    # ------------------------------------------------------------------
    # Buộc cập nhật (dùng khi setleaderboardchannel)
    # ------------------------------------------------------------------
    async def force_update(self, guild_id: int) -> None:
        await self._do_update(guild_id)

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------
    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                now = time.monotonic()
                for guild_id in list(self._pending):
                    last_change = self._pending.get(guild_id, 0)
                    last_update = self._last_update.get(guild_id, 0)
                    # Đã qua debounce -> cập nhật
                    if now - last_change >= min(DEBOUNCE_THRESHOLD, 30.0) and last_change > last_update:
                        await self._do_update(guild_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Lỗi trong LeaderboardUpdater loop")
                await asyncio.sleep(10)

    # ------------------------------------------------------------------
    # Cập nhật thực tế
    # ------------------------------------------------------------------
    async def _do_update(self, guild_id: int) -> None:
        lock = self._get_lock(guild_id)
        if lock.locked():
            return
        async with lock:
            self._last_update[guild_id] = time.monotonic()
            self._pending.pop(guild_id, None)

        try:
            config = await self.bot.config_manager.get(guild_id)
            lb_cfg = config.get("leaderboard", {})
            channel_id = lb_cfg.get("channel_id")
            message_id = lb_cfg.get("message_id")

            if not channel_id:
                return

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            service = self.bot.leveling_service
            if service is None:
                return

            top_docs = await service.get_top(guild_id, limit=TOP_LIMIT)

            entries: list[tuple[str, str, int]] = []
            for doc in top_docs:
                uid = doc.get("user_id", 0)
                user = self.bot.get_user(uid)
                if user is not None:
                    avatar = user.display_avatar.url
                    # Ưu tiên display_name, fallback về name
                    if isinstance(user, discord.Member):
                        name = user.display_name
                    else:
                        name = user.display_name if hasattr(user, "display_name") else user.name
                else:
                    avatar = ""
                    name = "Thành viên ẩn"
                entries.append((avatar, name, doc.get("total_xp", 0)))

            if not entries:
                return

            image = await service.build_leaderboard_image(guild_id, entries, top=3)
            file = discord.File(io.BytesIO(image), filename="leaderboard.png")

            if message_id:
                # Thử edit tin nhắn cũ
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(
                        content=None,
                        attachments=[file],
                        embed=None,
                    )
                    return
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    logger.warning("Không edit được leaderboard msg %s, gửi mới", message_id)

            # Gửi tin nhắn mới
            msg = await channel.send(file=file)
            await self.bot.config_manager.update(
                guild_id,
                {"leaderboard.message_id": msg.id},
            )

        except Exception:
            logger.exception("Lỗi cập nhật leaderboard cho guild %s", guild_id)
