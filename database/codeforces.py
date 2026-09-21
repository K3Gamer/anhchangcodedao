"""Quản lý cấu hình & trạng thái thông báo kỳ thi Codeforces cho từng server."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Nhắc "sắp bắt đầu" khi còn trong 1 giờ trước giờ thi
REMIND_BEFORE = 3600

DEFAULT_CODEFORCES: dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "ping_role_id": None,
    "notified": {},  # {contest_id: {"announced": bool, "reminded": bool}}
}


class CodeforcesRepository:
    """Truy xuất & ghi cấu hình thông báo Codeforces vào JSON (data/codeforces.json)."""

    def __init__(self, db: Any) -> None:
        self._collection = db["codeforces"]

    async def get(self, guild_id: int) -> dict[str, Any]:
        """Lấy cấu hình của server; tự tạo bản mặc định nếu chưa tồn tại."""
        doc = await self._collection.find_one({"_id": guild_id})
        if doc is None:
            doc = {"_id": guild_id, **deepcopy(DEFAULT_CODEFORCES)}
            await self._collection.insert_one(doc)
        return doc

    async def update(self, guild_id: int, updates: dict[str, Any]) -> None:
        """Cập nhật một hoặc nhiều trường (hỗ trợ đường dẫn lồng nhau)."""
        await self._collection.update_one({"_id": guild_id}, {"$set": updates}, upsert=True)

    async def set_notified(self, guild_id: int, contest_id: int, field: str, value: bool) -> None:
        """Đánh dấu một kỳ thi đã thông báo (`notified.<contest_id>.<field>`)."""
        await self._collection.update_one(
            {"_id": guild_id},
            {"$set": {f"notified.{contest_id}.{field}": value}},
            upsert=True,
        )

    async def get_enabled(self) -> list[dict[str, Any]]:
        """Danh sách cấu hình của các server đang bật thông báo."""
        return await self._collection.find({"enabled": True}).to_list()