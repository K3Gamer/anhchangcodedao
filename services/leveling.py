"""Nghiệp vụ XP/Level: công thức lên cấp, cộng XP, tính thứ hạng, nạp ảnh."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any

from database.leveling import LevelRepository
from utils.leaderboard_image import LeaderboardRenderer

# Công thức: level = sqrt(xp / 100)  -> level 1 cần 100 XP, level 2 cần 400 XP...
XP_PER_LEVEL = 100
MIN_XP = 15
MAX_XP = 25
XP_COOLDOWN_SECONDS = 60


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
        """Cộng XP cho thành viên (theo cooldown). Trả về dict level-up (None nếu không có)."""
        doc = await self.repository.get(guild_id, user_id)
        now = datetime.now(timezone.utc)

        if doc is not None:
            last = doc.get("last_message")
            if last is not None:
                age = (now - last).total_seconds()
                if age < XP_COOLDOWN_SECONDS:
                    return None
            xp = int(doc.get("total_xp", 0))
        else:
            xp = 0

        xp += self.roll_xp()

        new_doc: dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "total_xp": xp,
            "last_message": now,
        }
        await self.repository.upsert(new_doc)

        old_level = self.level_from_xp(xp - self.roll_xp())
        new_level = self.level_from_xp(xp)
        if new_level > old_level:
            return {
                "guild_id": guild_id,
                "user_id": user_id,
                "level": new_level,
                "xp": xp,
            }
        return {"guild_id": guild_id, "user_id": user_id, "level": new_level}

    async def get_user(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Trả về document XP/level của thành viên + còn thứ hạng."""
        doc = await self.repository.get(guild_id, user_id)
        if doc is None:
            return None
        doc["level"] = self.level_from_xp(doc.get("total_xp", 0))
        doc["rank"] = await self.repository.get_rank(guild_id, user_id)
        return doc

    async def get_top(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Danh sách top thành viên theo XP."""
        return await self.repository.get_top(guild_id, limit=limit)

    async def build_leaderboard_image(
        self, guild_id: int, entries: list[tuple[str, str, int]], top: int = 3
    ) -> bytes:
        """Nạp ảnh bảng xếp hạng (avatar url + tên + điểm theo từng dòng)."""
        if self._renderer is None:
            self._renderer = LeaderboardRenderer()
        enriched: list[tuple[str, str, int, float]] = []
        for url, name, total_xp in entries:
            _, _, _, ratio = self.level_progress(total_xp)
            enriched.append((url, name, total_xp, ratio))
        return await self._renderer.render(enriched, top=top)

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
        current_xp = int(doc.get("total_xp", 0)) if doc else 0
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
        current_xp = int(doc.get("total_xp", 0)) if doc else 0
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
