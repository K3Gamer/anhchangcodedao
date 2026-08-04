"""Kho dữ liệu cảnh cáo (Warn)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any


class WarnRepository:
    """Truy xuất & ghi dữ liệu cảnh cáo vào JSON (data/warns.json)."""

    def __init__(self, db: Any) -> None:
        self._collection = db["warns"]

    async def add(
        self, guild_id: int, user_id: int, moderator_id: int, reason: str
    ) -> dict[str, Any]:
        """Thêm một cảnh cáo mới, trả về document (kèm mã warn ngắn)."""
        doc: dict[str, Any] = {
            "_id": secrets.token_hex(3).upper(),
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "date": datetime.now(timezone.utc),
        }
        await self._collection.insert_one(doc)
        return doc

    async def get_all(self, guild_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
        """Lấy danh sách cảnh cáo (mới nhất trước)."""
        query: dict[str, Any] = {"guild_id": guild_id}
        if user_id is not None:
            query["user_id"] = user_id
        cursor = self._collection.find(query).sort("date", -1)
        return await cursor.to_list(length=None)

    async def count(self, guild_id: int, user_id: int) -> int:
        """Đếm số cảnh cáo của một thành viên."""
        return await self._collection.count_documents(
            {"guild_id": guild_id, "user_id": user_id}
        )

    async def remove(self, guild_id: int, warn_id: str) -> dict[str, Any] | None:
        """Xóa một cảnh cáo theo mã, trả về document đã xóa (nếu có)."""
        return await self._collection.find_one_and_delete(
            {"guild_id": guild_id, "_id": warn_id}
        )

    async def clear(self, guild_id: int, user_id: int) -> int:
        """Xóa toàn bộ cảnh cáo của một thành viên, trả về số lượng đã xóa."""
        result = await self._collection.delete_many(
            {"guild_id": guild_id, "user_id": user_id}
        )
        return result.deleted_count
