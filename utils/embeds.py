"""Trung tâm tạo Embed thống nhất cho toàn bot (Blurple, thumbnail, footer, timestamp)."""

from __future__ import annotations

from datetime import datetime, timezone

import discord

# Bảng màu chủ đạo
BLURPLE = discord.Color.from_rgb(88, 101, 242)
GREEN = discord.Color.from_rgb(87, 242, 135)
RED = discord.Color.from_rgb(242, 91, 91)
ORANGE = discord.Color.from_rgb(253, 175, 57)

COLOR_MAP: dict[str, discord.Color] = {
    "blurple": BLURPLE,
    "green": GREEN,
    "red": RED,
    "orange": ORANGE,
    "white": discord.Color.from_rgb(255, 255, 255),
}


class EmbedFactory:
    """Factory tạo Embed đồng nhất (thumbnail + footer + timestamp + màu Blurple)."""

    def __init__(self, bot: "CodiBot") -> None:
        self.bot = bot

    @property
    def _avatar(self) -> str | None:
        if self.bot.user is None:
            return None
        return self.bot.user.display_avatar.url

    @property
    def _name(self) -> str:
        return self.bot.user.name if self.bot.user else "Codi"

    def base(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        color: discord.Color = BLURPLE,
    ) -> discord.Embed:
        """Tạo embed gốc với đầy đủ thumbnail, footer, timestamp."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        avatar = self._avatar
        if avatar:
            embed.set_thumbnail(url=avatar)
            embed.set_footer(text=self._name, icon_url=avatar)
        return embed

    def success(self, description: str, title: str = "✅ Thành công") -> discord.Embed:
        """Embed báo thành công."""
        return self.base(title=title, description=description, color=GREEN)

    def error(self, description: str, title: str = "❌ Lỗi") -> discord.Embed:
        """Embed báo lỗi."""
        return self.base(title=title, description=description, color=RED)

    def warning(self, description: str, title: str = "⚠️ Cảnh báo") -> discord.Embed:
        """Embed cảnh báo."""
        return self.base(title=title, description=description, color=ORANGE)

    def info(self, description: str, title: str = "ℹ️ Thông tin") -> discord.Embed:
        """Embed thông tin."""
        return self.base(title=title, description=description, color=BLURPLE)
