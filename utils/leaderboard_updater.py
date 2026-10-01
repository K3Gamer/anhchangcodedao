"""Tự động cập nhật leaderboard trong kênh đã cấu hình.

Mọi thay đổi XP đều đi qua notify_xp_change() (hoặc force_update() khi admin
đổi dữ liệu). Mục tiêu: không được bỏ sót thay đổi nào.

Quy tắc:
- Mỗi server có một lock riêng, giữ xuyên suốt quá trình cập nhật để không
  gửi trùng tin nhắn.
- Nếu có thay đổi mới đến lúc đang cập nhật, thay đổi đó được giữ lại và
  cập nhật tiếp ngay sau (không bị bỏ rơi).
- Thay đổi rải rác trong DEBOUNCE_THRESHOLD giây sẽ gộp lại thành một lần
  cập nhật; thay đổi đầu tiên sau thời gian chờ sẽ cập nhật ngay.
- Luôn ghi lại ảnh, kể cả khi không còn ai có XP, để tin nhắn đã ghim không
  bị treo dữ liệu cũ.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import TYPE_CHECKING, Any

import discord

from services.leveling import LEADERBOARD_SIZE

if TYPE_CHECKING:
    from core.bot import CodiBot

logger = logging.getLogger("codi")

DEBOUNCE_THRESHOLD = 30.0  # giây — gộp các thay đổi liên tiếp trong khoảng này
POLL_INTERVAL = 5.0  # giây — chu kỳ quét thay đổi đang chờ
TOP_LIMIT = LEADERBOARD_SIZE


class LeaderboardUpdater:
    """Theo dõi thay đổi XP và tự động cập nhật ảnh leaderboard."""

    def __init__(self, bot: CodiBot) -> None:
        self.bot = bot
        self._pending: dict[int, float] = {}  # guild_id -> lần thay đổi gần nhất
        self._last_update: dict[int, float] = {}  # guild_id -> lần cập nhật cuối
        self._locks: dict[int, asyncio.Lock] = {}
        self._task: asyncio.Task[None] | None = None
        self._closing = False

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    # ------------------------------------------------------------------
    # Khởi động / dừng background task
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._closing = False
            self._task = asyncio.create_task(self._loop(), name="leaderboard-updater")

    async def stop(self) -> None:
        """Dừng background task và chờ nó kết thúc cho sạch."""
        self._closing = True
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("LeaderboardUpdater dừng với lỗi nhỏ", exc_info=True)

    # ------------------------------------------------------------------
    # Nguồn phát tín hiệu thay đổi
    # ------------------------------------------------------------------
    async def notify_xp_change(self, guild_id: int) -> None:
        """Được gọi mỗi khi XP của server thay đổi."""
        if self._closing:
            return
        now = time.monotonic()
        self._pending[guild_id] = now

        # Nếu đã lâu không cập nhật thì làm ngay, còn lại để loop gộp lại.
        if now - self._last_update.get(guild_id, 0.0) >= DEBOUNCE_THRESHOLD:
            await self._do_update(guild_id)

    async def force_update(self, guild_id: int) -> None:
        """Cập nhật ngay, bỏ qua debounce (dùng khi admin đổi XP / cấu hình)."""
        self._pending[guild_id] = time.monotonic()
        await self._do_update(guild_id)

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------
    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL)
                await self._drain()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Lỗi trong LeaderboardUpdater loop")
                await asyncio.sleep(10)

    async def _drain(self) -> None:
        """Cập nhật mọi server đang chờ đã đủ thời gian gộp."""
        self._forget_unknown_guilds()
        now = time.monotonic()
        for guild_id, changed_at in list(self._pending.items()):
            if now - changed_at < DEBOUNCE_THRESHOLD:
                continue
            try:
                await self._do_update(guild_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Không cập nhật được leaderboard cho guild %s", guild_id)

    def _forget_unknown_guilds(self) -> None:
        """Bỏ trạng thái của server bot không còn ở trong để không phình bộ nhớ."""
        self.forget_all_except({g.id for g in self.bot.guilds})

    # ------------------------------------------------------------------
    # Cập nhật thực tế
    # ------------------------------------------------------------------
    async def _do_update(self, guild_id: int) -> None:
        """Vẽ và gửi lại bảng xếp hạng của một server (nếu đã cấu hình kênh)."""
        if self._closing:
            return

        lock = self._get_lock(guild_id)
        # Chờ lock thay vì bỏ qua: nếu đang cập nhật thì thay đổi mới phải được
        # xử lý sau, không được âm thầm rơi mất.
        async with lock:
            try:
                await self._update_locked(guild_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Lỗi cập nhật leaderboard cho guild %s", guild_id)

    async def _update_locked(self, guild_id: int) -> None:
        """Thân của _do_update, chạy khi đã giữ lock của server."""
        self._pending.pop(guild_id, None)
        self._last_update[guild_id] = time.monotonic()

        config = await self._get_channel_config(guild_id)
        if config is None:
            return
        channel_id, message_id = config

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        service = self.bot.leveling_service
        if service is None:
            return

        _, image = await service.render_leaderboard(guild, limit=TOP_LIMIT, top=3)
        file = discord.File(io.BytesIO(image), filename="leaderboard.png")

        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=None, attachments=[file], embed=None)
                return
            except discord.NotFound:
                pass  # Tin nhắn bị xoá -> gửi lại mới
            except discord.Forbidden:
                logger.warning("Không có quyền sửa leaderboard msg %s", message_id)
                return
            except discord.HTTPException:
                logger.warning("Không sửa được leaderboard msg %s, sẽ gửi mới", message_id)

        msg = await channel.send(file=file)
        await self.bot.config_manager.update(guild_id, {"leaderboard.message_id": msg.id})

    async def _get_channel_config(self, guild_id: int) -> tuple[int, int | None] | None:
        """Đọc cấu hình leaderboard, trả None nếu server chưa đặt kênh."""
        config = await self.bot.config_manager.get(guild_id)
        lb_cfg = config.get("leaderboard") or {}
        channel_id = lb_cfg.get("channel_id")
        if not channel_id:
            return None
        return int(channel_id), lb_cfg.get("message_id")

    # ------------------------------------------------------------------
    # Dọn bộ nhớ
    # ------------------------------------------------------------------
    def forget(self, guild_id: int) -> None:
        """Xoá trạng thái của một server (dùng khi bot bị gỡ khỏi server)."""
        self._pending.pop(guild_id, None)
        self._last_update.pop(guild_id, None)
        self._locks.pop(guild_id, None)

    def forget_all_except(self, guild_ids: set[int]) -> None:
        """Bỏ trạng thái của các server bot không còn ở trong."""
        stale = {gid for gid in self._last_update if gid not in guild_ids}
        stale |= {gid for gid in self._pending if gid not in guild_ids}
        stale |= {gid for gid in self._locks if gid not in guild_ids}
        for guild_id in stale:
            self.forget(guild_id)