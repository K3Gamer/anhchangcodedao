"""Tập hợp các exception tùy chỉnh của bot."""

from __future__ import annotations

from typing import Iterable


class BotError(Exception):
    """Lỗi chung có thể hiển thị trực tiếp cho người dùng."""


class MissingBotPermissionsError(BotError):
    """Bot thiếu quyền thực hiện hành động."""

    def __init__(self, permissions: Iterable[str]) -> None:
        self.permissions = list(permissions)
        super().__init__(f"Bot thiếu quyền: {', '.join(self.permissions)}")


class NotBotOwnerError(BotError):
    """Người dùng không phải chủ sở hữu bot."""
