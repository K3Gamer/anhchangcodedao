"""Bộ nhớ đệm TTL đơn giản trong RAM."""

from __future__ import annotations

import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Cache trong RAM với thời gian sống (TTL) để giảm truy vấn MongoDB.

    Thread-safe không bắt buộc vì mọi truy cập đều chạy trong event loop.
    """

    def __init__(self, ttl: float = 120.0) -> None:
        self.ttl = ttl
        self._store: dict[Any, tuple[T, float]] = {}

    def get(self, key: Any) -> T | None:
        """Lấy giá trị; trả None nếu hết hạn hoặc không tồn tại."""
        item = self._store.get(key)
        if item is None:
            return None
        value, expires = item
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: Any, value: T) -> None:
        """Ghi giá trị kèm thời điểm hết hạn."""
        self._store[key] = (value, time.monotonic() + self.ttl)

    def delete(self, key: Any) -> None:
        """Xóa một khóa."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Xóa toàn bộ cache."""
        self._store.clear()
