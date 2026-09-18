"""Tiện ích xử lý chuỗi."""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Iterable

from utils.constants import BAD_WORDS

# Biểu tượng thay thế từ bậy
BONK_ICON = ":bonk:"


def slugify(text: str, limit: int = 24) -> str:
    """Chuyển chuỗi thành slug an toàn cho tên kênh Discord."""
    slug = re.sub(r"[^a-zA-Z0-9\-]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-")


def truncate(text: str, limit: int = 1000) -> str:
    """Cắt chuỗi về độ dài tối đa, thêm dấu ba chấm nếu bị cắt."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def escape(text: str) -> str:
    """HTML-escape chuỗi (dùng khi tạo transcript)."""
    return html_module.escape(text, quote=True)


def censor_bad_words(text: str, bad_words: Iterable[str] = BAD_WORDS) -> tuple[str, int]:
    """Thay mọi từ bậy trong chuỗi bằng icon :bonk:.

    Trả về (nội dung đã thay thế, số từ bậy bị phát hiện).
    So khớp không phân biệt hoa thường và ưu tiên thay từ dài trước.
    """
    censored = text
    count = 0
    for word in sorted(bad_words, key=len, reverse=True):
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        censored, n = pattern.subn(BONK_ICON, censored)
        count += n
    return censored, count


_PERMISSION_NAMES: dict[str, str] = {
    "administrator": "Administrator",
    "ban_members": "Ban Members",
    "kick_members": "Kick Members",
    "manage_messages": "Manage Messages",
    "manage_channels": "Manage Channels",
    "manage_roles": "Manage Roles",
    "manage_nicknames": "Manage Nicknames",
    "moderate_members": "Moderate Members",
    "manage_guild": "Manage Server",
    "move_members": "Move Members",
    "manage_webhooks": "Manage Webhooks",
    "manage_emojis_and_stickers": "Manage Emojis & Stickers",
}


def permission_names(permissions: list[str]) -> str:
    """Chuyển danh sách quyền thành tên dễ đọc."""
    return ", ".join(
        _PERMISSION_NAMES.get(p, p.replace("_", " ").title()) for p in permissions
    )
