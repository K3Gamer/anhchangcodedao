"""Kho dữ liệu Ticket."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TicketRepository:
    """Truy xuất & ghi dữ liệu ticket vào JSON (data/tickets.json)."""

    def __init__(self, db: Any) -> None:
        self._collection = db["tickets"]

    async def create(
        self,
        channel_id: int,
        guild_id: int,
        user_id: int,
        ticket_type: str,
        welcome_message_id: int | None = None,
    ) -> dict[str, Any]:
        """Tạo bản ghi ticket (khóa chính là ID channel)."""
        doc: dict[str, Any] = {
            "_id": channel_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "ticket_type": ticket_type,
            "welcome_message_id": welcome_message_id,
            "opened_at": datetime.now(timezone.utc),
        }
        await self._collection.insert_one(doc)
        return doc

    async def get_by_user(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Tìm ticket đang mở của một người dùng (mỗi người chỉ được 1 ticket)."""
        return await self._collection.find_one(
            {"guild_id": guild_id, "user_id": user_id}
        )

    async def get_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        """Tìm ticket theo channel."""
        return await self._collection.find_one({"_id": channel_id})

    async def close(self, channel_id: int) -> None:
        """Xóa bản ghi ticket (khi đã đóng)."""
        await self._collection.delete_one({"_id": channel_id})

    async def open_tickets(self, guild_id: int) -> list[dict[str, Any]]:
        """Lấy toàn bộ ticket đang mở của một server."""
        cursor = self._collection.find({"guild_id": guild_id})
        return await cursor.to_list(length=None)
