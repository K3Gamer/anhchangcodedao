"""Tiện ích xử lý thời gian."""

from __future__ import annotations

import re

# Đơn vị thời gian (hỗ trợ cả tiếng Anh lẫn tiếng Việt)
TIME_UNITS: dict[str, int] = {
    "s": 1, "giây": 1,
    "m": 60, "phút": 60,
    "h": 3600, "giờ": 3600,
    "d": 86400, "ngày": 86400,
    "w": 604800, "tuần": 604800,
}

_TOKEN_RE = re.compile(
    r"(\d+)\s*(s|giây|m|phút|h|giờ|d|ngày|w|tuần)",
    re.IGNORECASE,
)


def parse_duration(text: str) -> int | None:
    """Chuyển chuỗi thời gian (vd: '1h30m', '2 ngày', '45m') thành số giây.

    Trả về None nếu định dạng không hợp lệ.
    """
    matches = _TOKEN_RE.findall(text.lower().strip())
    if not matches:
        return None
    total = 0
    for value, unit in matches:
        total += int(value) * TIME_UNITS[unit]
    return total


def format_duration(seconds: float) -> str:
    """Định dạng số giây thành chuỗi dễ đọc (vd: '2 ngày 3 giờ 10 phút')."""
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if minutes:
        parts.append(f"{minutes} phút")
    if sec and not parts:
        parts.append(f"{sec} giây")
    return " ".join(parts) or "0 giây"
