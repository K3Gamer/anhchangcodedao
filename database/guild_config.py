"""Quản lý cấu hình từng server (Guild Config) kèm cache TTL."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from utils.cache import TTLCache
from utils.constants import DEFAULT_PREFIX

# ---------------------------------------------------------------
# Cấu hình mặc định cho từng server
# ---------------------------------------------------------------

DEFAULT_AUTOMOD: dict[str, Any] = {
    "enabled": True,
    "anti_spam": {"enabled": True, "max_messages": 6, "interval": 8, "action": "delete"},
    "anti_mention": {"enabled": True, "max_mentions": 6, "action": "delete"},
    "anti_link": {"enabled": True, "action": "delete"},
    "anti_invite": {"enabled": True, "action": "delete"},
    "anti_scam": {"enabled": True, "action": "delete"},
    "anti_emoji": {"enabled": True, "max_emojis": 15, "action": "delete"},
    "anti_caps": {"enabled": True, "max_percent": 0.7, "min_chars": 8, "action": "delete"},
    "anti_badwords": {"enabled": True, "action": "delete"},
    "anti_flood": {"enabled": True, "max_duplicates": 4, "interval": 20, "action": "delete"},
    "auto_slowmode": {"enabled": False, "threshold": 8, "window": 10, "slowmode_seconds": 10},
    "whitelisted_channels": [],
    "whitelisted_users": [],
    "whitelisted_roles": [],
}

DEFAULT_ANTINUKE: dict[str, Any] = {
    "enabled": True,
    "window": 10,
    "action": "ban",
    "max_bans": 5,
    "max_kicks": 5,
    "max_channel_delete": 3,
    "max_channel_create": 3,
    "max_role_delete": 3,
    "max_role_create": 3,
    "max_emoji_delete": 3,
    "max_sticker_delete": 3,
    "max_webhook_delete": 3,
    "max_permission_edit": 8,
    "whitelisted_users": [],
    "whitelisted_roles": [],
}

DEFAULT_GUILD_CONFIG: dict[str, Any] = {
    "prefix": DEFAULT_PREFIX,
    "mod_log_channel": None,
    "logging_channel": None,
    "logging": {"enabled": True, "events": {}},
    "ticket": {
        "category_id": None,
        "staff_role_id": None,
        "transcript_channel_id": None,
        "panel_channel_id": None,
        "panel_message_id": None,
    },
    "leaderboard": {
        "channel_id": None,
        "message_id": None,
    },
    "automod": DEFAULT_AUTOMOD,
    "antinuke": DEFAULT_ANTINUKE,
}


class GuildConfigRepository:
    """Truy xuất & ghi cấu hình server vào JSON (data/guild_configs.json)."""

    def __init__(self, db: Any) -> None:
        self._collection = db["guild_configs"]

    async def get_or_create(self, guild_id: int) -> dict[str, Any]:
        """Lấy cấu hình; tạo cấu hình mặc định nếu chưa tồn tại."""
        doc = await self._collection.find_one({"_id": guild_id})
        if doc is None:
            doc = self._default(guild_id)
            await self._collection.insert_one(doc)
        return doc

    async def update(self, guild_id: int, updates: dict[str, Any]) -> None:
        """Cập nhật một hoặc nhiều trường (hỗ trợ đường dẫn lồng nhau như 'automod.anti_spam.enabled')."""
        await self._collection.update_one({"_id": guild_id}, {"$set": updates}, upsert=True)

    @staticmethod
    def _default(guild_id: int) -> dict[str, Any]:
        return {"_id": guild_id, **deepcopy(DEFAULT_GUILD_CONFIG)}


class GuildConfigManager:
    """Quản lý cấu hình server với cache TTL để giảm đọc file."""

    def __init__(self, db: Any) -> None:
        self._repo = GuildConfigRepository(db)
        self._cache: TTLCache[dict[str, Any]] = TTLCache(ttl=120)

    async def get(self, guild_id: int) -> dict[str, Any]:
        """Lấy cấu hình (cache 120s, tự động tạo mặc định nếu chưa có)."""
        cached = self._cache.get(guild_id)
        if cached is not None:
            return cached
        doc = await self._repo.get_or_create(guild_id)
        self._cache.set(guild_id, doc)
        return doc

    async def update(self, guild_id: int, updates: dict[str, Any]) -> None:
        """Cập nhật cấu hình rồi làm mới cache ngay lập tức."""
        await self._repo.update(guild_id, updates)
        self._cache.delete(guild_id)

    def invalidate(self, guild_id: int) -> None:
        """Xóa cache của một server."""
        self._cache.delete(guild_id)
