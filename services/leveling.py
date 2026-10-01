"""Nghiệp vụ XP/Level: công thức lên cấp, cộng XP, tính thứ hạng, nạp ảnh."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any

import discord

from database.leveling import LevelRepository
from utils.leaderboard_image import LeaderboardRenderer

# Công thức: level = sqrt(xp / 100)  -> level 1 cần 100 XP, level 2 cần 400 XP...
XP_PER_LEVEL = 100
MIN_XP = 15
MAX_XP = 25
XP_COOLDOWN_SECONDS = 60

# Số dòng hiển thị mặc định trên bảng xếp hạng
LEADERBOARD_SIZE = 10
# Lấy dư ra bên trong để bù cho thành viên đã rời server bị loại khỏi danh sách
LEADERBOARD_OVERFETCH = 3
EMPTY_TITLE = "Chưa có ai tích lũy XP"


class LevelingService:
    """Xử lý mọi logic XP/Level cho toàn bot."""

    def __init__(self, db: Any) -> None:
        self.repository = LevelRepository(db)
        self._renderer: LeaderboardRenderer | None = None

    # ---------------------------------------------------------------
    # Công thức
    # ---------------------------------------------------------------
    @staticmethod
    def xp_for_level(level: int) -> float:
        """Tổng XP tối thiểu để đạt một level nhất định."""
        return XP_PER_LEVEL * (level**2)

    @staticmethod
    def level_from_xp(xp: int) -> int:
        """Chuyển tổng XP sang level."""
        return int(math.sqrt(xp / XP_PER_LEVEL))

    @staticmethod
    def level_progress(xp: int) -> tuple[int, int, int, float]:
        """Trả về (level, xp_hiện_tại_trong_level, xp_cần_cho_level_kế, tỉ_lệ 0-1)."""
        level = LevelingService.level_from_xp(xp)
        base = LevelingService.xp_for_level(level)
        nxt = LevelingService.xp_for_level(level + 1)
        in_level = xp - base
        span = nxt - base
        ratio = in_level / span if span else 0.0
        return level, in_level, span, ratio

    @staticmethod
    def roll_xp() -> int:
        """Lượng XP cho một tin nhắn (ngẫu nhiên trong khoảng MIN..MAX)."""
        return random.randint(MIN_XP, MAX_XP)

    # ---------------------------------------------------------------
    # Thao tác
    # ---------------------------------------------------------------
    async def grant_xp(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Cộng XP cho thành viên (theo cooldown).

        Trả về None nếu đang trong thời gian chờ (XP không đổi), ngược lại trả về
        thông tin XP mới kèm cờ 'level_up'.
        """
        doc = await self.repository.get(guild_id, user_id)
        now = datetime.now(timezone.utc)

        if doc is not None:
            last = doc.get("last_message")
            if last is not None:
                age = (now - last).total_seconds()
                if age < XP_COOLDOWN_SECONDS:
                    return None
            xp_current = int(doc.get("total_xp") or 0)
        else:
            xp_current = 0

        delta_xp = self.roll_xp()
        xp_new = xp_current + delta_xp

        new_doc: dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "total_xp": xp_new,
            "last_message": now,
        }
        await self.repository.upsert(new_doc)

        old_level = self.level_from_xp(xp_current)
        new_level = self.level_from_xp(xp_new)
        return {
            "guild_id": guild_id,
            "user_id": user_id,
            "level": new_level,
            "old_level": old_level,
            "level_up": new_level > old_level,
            "xp": xp_new,
            "delta": delta_xp,
        }

    async def get_user(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Trả về document XP/level của thành viên + còn thứ hạng."""
        doc = await self.repository.get(guild_id, user_id)
        if doc is None:
            return None
        doc["level"] = self.level_from_xp(int(doc.get("total_xp") or 0))
        doc["rank"] = await self.repository.get_rank(guild_id, user_id)
        return doc

    async def get_top(self, guild_id: int, limit: int = LEADERBOARD_SIZE) -> list[dict[str, Any]]:
        """Danh sách top thành viên theo XP."""
        return await self.repository.get_top(guild_id, limit=limit)

    @staticmethod
    def build_entries(
        guild: discord.Guild, docs: list[dict[str, Any]]
    ) -> list[tuple[str, str, int]]:
        """Chuyển document XP thành các dòng cho ảnh leaderboard.

        Bỏ qua thành viên không còn trong server để bảng xếp hạng luôn khớp với
        thành viên thực tế. Nhờ vậy /leaderboard và bảng trong kênh tự động có
        cùng một nguồn dữ liệu, không thể lệch nhau.
        """
        entries: list[tuple[str, str, int]] = []
        for doc in docs:
            member = guild.get_member(int(doc.get("user_id") or 0))
            if member is None:
                continue
            entries.append(
                (
                    member.display_avatar.url,
                    member.display_name,
                    int(doc.get("total_xp") or 0),
                )
            )
        return entries

    async def build_leaderboard_image(
        self,
        guild_id: int,
        entries: list[tuple[str, str, int]],
        top: int = 3,
        title: str = "Bảng xếp hạng XP",
    ) -> bytes:
        """Nạp ảnh bảng xếp hạng (avatar url + tên + điểm theo từng dòng)."""
        if self._renderer is None:
            self._renderer = LeaderboardRenderer()
        enriched: list[tuple[str, str, int, float]] = []
        for url, name, total_xp in entries:
            _, _, _, ratio = self.level_progress(total_xp)
            enriched.append((url, name, total_xp, ratio))
        return await self._renderer.render(enriched, top=top, title=title)

    async def render_leaderboard(
        self,
        guild: discord.Guild,
        limit: int = LEADERBOARD_SIZE,
        top: int = 3,
    ) -> tuple[list[tuple[str, str, int]], bytes]:
        """Lấy top thành viên rồi vẽ ảnh, trả về (các dòng, bytes PNG).

        Khi chưa ai có XP vẫn trả về ảnh (tiêu đề kiểu "chưa có dữ liệu") để tin
        nhắn đã ghim không bị treo dữ liệu cũ.
        """
        docs = await self.get_top(guild.id, limit=limit * LEADERBOARD_OVERFETCH)
        entries = self.build_entries(guild, docs)[:limit]
        title = "Bảng xếp hạng XP" if entries else EMPTY_TITLE
        image = await self.build_leaderboard_image(guild.id, entries, top=top, title=title)
        return entries, image

    async def reset_guild(self, guild_id: int) -> int:
        return await self.repository.reset_guild(guild_id)

    async def reset_user(self, guild_id: int, user_id: int) -> bool:
        return await self.repository.reset_user(guild_id, user_id)

    # ---------------------------------------------------------------
    # Thao tác XP thủ công (admin)
    # ---------------------------------------------------------------
    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> dict[str, Any]:
        """Cộng XP thủ công. Trả về doc sau khi cập nhật."""
        doc = await self.repository.get(guild_id, user_id)
        current_xp = int(doc.get("total_xp") or 0) if doc else 0
        new_xp = max(0, current_xp + amount)
        new_doc: dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "total_xp": new_xp,
        }
        if doc is None:
            new_doc["last_message"] = datetime.now(timezone.utc)
        await self.repository.upsert(new_doc)
        new_doc["level"] = self.level_from_xp(new_xp)
        new_doc["old_level"] = self.level_from_xp(current_xp)
        return new_doc

    async def remove_xp(self, guild_id: int, user_id: int, amount: int) -> dict[str, Any]:
        """Trừ XP thủ công. Trả về doc sau khi cập nhật."""
        return await self.add_xp(guild_id, user_id, -amount)

    async def set_xp(self, guild_id: int, user_id: int, amount: int) -> dict[str, Any]:
        """Đặt XP thủ công. Trả về doc sau khi cập nhật."""
        amount = max(0, amount)
        doc = await self.repository.get(guild_id, user_id)
        current_xp = int(doc.get("total_xp") or 0) if doc else 0
        new_doc: dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "total_xp": amount,
        }
        if doc is None:
            new_doc["last_message"] = datetime.now(timezone.utc)
        await self.repository.upsert(new_doc)
        new_doc["level"] = self.level_from_xp(amount)
        new_doc["old_level"] = self.level_from_xp(current_xp)
        return new_doc
