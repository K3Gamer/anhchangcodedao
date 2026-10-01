"""Kho dữ liệu XP & Level của hệ thống bảng xếp hạng (data/levels.json)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class LevelRepository:
    """Truy xuất & ghi dữ liệu XP theo từng thành viên trong mỗi server."""

    def __init__(self, db: Any) -> None:
        self._collection = db["levels"]

    # ---------------------------------------------------------------
    # Đọc
    # ---------------------------------------------------------------
    async def get(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Lấy document XP/level của một thành viên (None nếu chưa có)."""
        return await self._collection.find_one(
            {"guild_id": guild_id, "user_id": user_id}
        )

    async def get_top(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Lấy danh sách thành viên xếp hạng theo tổng XP (cao nhất trước).

        Chỉ trả về thành viên đang có XP (> 0). Khi bằng XP thì sắp theo user_id
        để thứ tự luôn ổn định giữa các lần cập nhật.
        """
        if limit is not None and limit <= 0:
            return []
        cursor = self._collection.find(
            {"guild_id": guild_id, "total_xp": {"$gt": 0}}
        ).sort(("total_xp", "user_id"), -1)
        return await cursor.to_list(length=limit)

    async def get_rank(self, guild_id: int, user_id: int) -> int:
        """Trả về thứ hạng của thành viên (1 = cao nhất). 0 nếu chưa có XP.

        Thứ hạng = 1 + số thành viên có XP cao hơn. Thành viên bằng XP sẽ
        dùng chung một thứ hạng (1, 2, 2, 4...).
        """
        me = await self.get(guild_id, user_id)
        if me is None:
            return 0
        my_xp = int(me.get("total_xp") or 0)
        if my_xp <= 0:
            return 0
        above = await self._collection.count_documents(
            {
                "guild_id": guild_id,
                "user_id": {"$ne": user_id},
                "total_xp": {"$gt": my_xp},
            }
        )
        return above + 1

    # ---------------------------------------------------------------
    # Ghi
    # ---------------------------------------------------------------
    async def upsert(self, doc: dict[str, Any]) -> None:
        """Tạo mới hoặc cập nhật document XP cho một thành viên."""
        await self._collection.update_one(
            {"guild_id": doc["guild_id"], "user_id": doc["user_id"]},
            {"$set": doc},
            upsert=True,
        )

    async def reset_guild(self, guild_id: int) -> int:
        """Xóa toàn bộ dữ liệu XP của một server, trả về số bản ghi đã xóa."""
        result = await self._collection.delete_many({"guild_id": guild_id})
        return result.deleted_count

    async def reset_user(self, guild_id: int, user_id: int) -> bool:
        """Xóa dữ liệu XP của một thành viên, trả về True nếu có xóa."""
        result = await self._collection.delete_one(
            {"guild_id": guild_id, "user_id": user_id}
        )
        return result.deleted_count > 0
