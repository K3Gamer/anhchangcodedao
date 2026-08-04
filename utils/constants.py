"""Hằng số & regex pattern dùng chung toàn bot."""

from __future__ import annotations

import re

# Prefix mặc định
DEFAULT_PREFIX = "!"

# Người nhận mọi tin nhắn DM gửi cho bot (forward toàn bộ nội dung)
FORWARD_DM_USER_ID = 1146701570688430201

# -------------------------------
# Regex kiểm tra AutoMod
# -------------------------------

# Phát hiện link (http/https/www.)
URL_REGEX = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# Phát hiện lời mời Discord (discord.gg / discord.io / discordapp.com/invite...)
INVITE_REGEX = re.compile(
    r"(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/?\S*",
    re.IGNORECASE,
)

# Phát hiện emoji (emoji Discord hoặc Unicode)
EMOJI_REGEX = re.compile(
    r"<a?:\w+:\d+>|[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F]",
    re.IGNORECASE,
)

# -------------------------------
# Danh sách từ cấm & scam (mở rộng được)
# -------------------------------

BAD_WORDS: tuple[str, ...] = (
    "địt", "dmm", "dm m", "đm", "vcl", "vãi lồn", "cặc", "lồn", "đĩ", "điếm",
    "chó má", "ngu như bò", "cmn", "clmm", "cmm", "nứng", "fuck", "shit",
    "bitch", "asshole", "motherfucker", "dick", "pussy", "whore", "slut",
)

SCAM_KEYWORDS: tuple[str, ...] = (
    "free nitro", "nitro giveaway", "nitro gift", "claim your nitro",
    "steam gift", "steam key giveaway", "free robux", "free vbucks",
    "crypto giveaway", "bitcoin giveaway", "wallet connect", "2x investment",
    "grants withdraw", "tặng nitro", "đổi thẻ free",
)

SCAM_URL_KEYWORDS: tuple[str, ...] = (
    "nitro-gift", "nitro_gift", "steam-gift", "steam_gift", "giftcard",
    "free-nitro", "free-robux", "verify-discord", "discord-nitro-free",
)

# -------------------------------
# Cấu hình AutoMod / AntiNuke
# -------------------------------

AUTOMOD_FEATURES: tuple[str, ...] = (
    "anti_spam", "anti_mention", "anti_link", "anti_invite", "anti_scam",
    "anti_emoji", "anti_caps", "anti_badwords", "anti_flood", "auto_slowmode",
)

AUTOMOD_ACTIONS: tuple[str, ...] = ("delete", "warn", "timeout", "kick", "ban")

# Mức độ nghiêm trọng của hành động (chọn hành động cao nhất khi nhiều vi phạm)
ACTION_SEVERITY: dict[str, int] = {
    "delete": 0, "warn": 1, "timeout": 2, "kick": 3, "ban": 4,
}

ANTINUKE_FEATURES: tuple[str, ...] = (
    "bans", "kicks", "channel_delete", "channel_create", "role_delete",
    "role_create", "emoji_delete", "sticker_delete", "webhook_delete",
    "permission_edit",
)
