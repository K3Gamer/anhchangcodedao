"""Sinh ảnh bảng xếp hạng hiện đại với Pillow.

Thiết kế mới: nền tối hiện đại, card phẳng, avatar tròn,
rank number lớn, tên + XP rõ ràng, thanh tiến trình ở dưới mỗi hàng.
Top 3 được viền màu vàng/bạc/đồng.
"""

from __future__ import annotations

import asyncio
import io
import os
import platform

import aiohttp
from PIL import Image, ImageDraw, ImageFont

# ── Bảng màu ──────────────────────────────────────────────────
BG_DARK = (30, 31, 38)          # nền chính
BG_CARD = (35, 36, 44)          # nền mỗi hàng
BG_CARD_TOP3 = (40, 41, 52)    # nền top 3
BORDER_TOP1 = (255, 215, 0)     # vàng
BORDER_TOP2 = (192, 192, 192)   # bạc
BORDER_TOP3 = (205, 127, 50)    # đồng
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (150, 155, 175)
TEXT_XP = (120, 200, 120)
BAR_BG = (50, 52, 65)
BAR_FILL = (88, 101, 242)       # Blurple
BAR_FILL_TOP1 = (255, 215, 0)
BAR_FILL_TOP2 = (192, 192, 192)
BAR_FILL_TOP3 = (205, 127, 50)
DIVIDER = (55, 56, 66)

ROW_H = 90
PAD_X = 24
PAD_Y = 20
CARD_RADIUS = 12


def _rounded_avatar(img: Image.Image, size: int) -> Image.Image:
    """Cắt ảnh vuông bo tròn hoàn toàn."""
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


async def _fetch_avatar(session: aiohttp.ClientSession, url: str) -> Image.Image:
    """Tải avatar; fallback về hình tròn mặc định nếu lỗi."""
    default = Image.new("RGBA", (256, 256), (88, 101, 242, 255))
    if not url:
        return default
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return default
            data = await resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        return img
    except Exception:
        return default


def _load_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font hệ thống hỗ trợ tiếng Việt."""
    if weight == "bold":
        candidates = [
            ("DejaVuSans-Bold.ttf", "DejaVuSans-Bold"),
            ("arialbd.ttf", "Arial Bold"),
            ("segoeuib.ttf", "Segoe UI Bold"),
            ("LiberationSans-Bold.ttf", "LiberationSans-Bold"),
            ("NotoSans-Bold.ttf", "NotoSans-Bold"),
        ]
    else:
        candidates = [
            ("DejaVuSans.ttf", "DejaVuSans"),
            ("arial.ttf", "Arial"),
            ("segoeui.ttf", "Segoe UI"),
            ("LiberationSans-Regular.ttf", "LiberationSans"),
            ("NotoSans-Regular.ttf", "NotoSans"),
        ]

    search_dirs = [
        "C:\\Windows\\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts",
        "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
    ]

    for fname, _ in candidates:
        for d in search_dirs:
            p = os.path.join(d, fname)
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple,
    outline: tuple | None = None,
    width: int = 0,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


class LeaderboardRenderer:
    """Vẽ ảnh leaderboard."""

    async def render(
        self,
        entries: list[tuple[str, str, int, float]],
        top: int = 3,
        title: str = "Bảng xếp hạng XP",
    ) -> bytes:
        """entries: [(avatar_url, name, total_xp, progress_ratio)]. Trả về bytes PNG."""
        font_title = _load_font(38, "bold")
        font_sub = _load_font(18)
        font_rank = _load_font(32, "bold")
        font_name = _load_font(22, "bold")
        font_xp = _load_font(18)
        font_level = _load_font(14)
        font_medal_num = _load_font(20, "bold")

        n = len(entries)
        width = 620
        header_h = 120
        height = header_h + n * ROW_H + PAD_Y * 2

        # ── Nền ──
        img = Image.new("RGBA", (width, height), BG_DARK)
        draw = ImageDraw.Draw(img)

        # ── Header ──
        draw.text((PAD_X + 4, 28), title, font=font_title, fill=TEXT_WHITE)
        draw.text(
            (PAD_X + 4, 76),
            f"{n} thành viên",
            font=font_sub,
            fill=TEXT_GRAY,
        )

        # ── Divider ──
        draw.line(
            (PAD_X, header_h - 8, width - PAD_X, header_h - 8),
            fill=DIVIDER,
            width=1,
        )

        # ── Tải avatar ──
        async with aiohttp.ClientSession() as session:
            avatars = await asyncio.gather(
                *[_fetch_avatar(session, url) for url, _, _, _ in entries]
            )

        # ── Vẽ mỗi hàng ──
        medal_border = {1: BORDER_TOP1, 2: BORDER_TOP2, 3: BORDER_TOP3}
        medal_bar = {1: BAR_FILL_TOP1, 2: BAR_FILL_TOP2, 3: BAR_FILL_TOP3}

        for i, ((url, name, total_xp, ratio), avatar_raw) in enumerate(zip(entries, avatars)):
            y = header_h + PAD_Y + i * ROW_H
            rank_num = i + 1
            is_top3 = rank_num <= top

            # ── Card nền ──
            card_fill = BG_CARD_TOP3 if is_top3 else BG_CARD
            card_outline = medal_border.get(rank_num) if is_top3 else None
            _draw_rounded_rect(
                draw,
                (PAD_X, y, width - PAD_X, y + ROW_H - 6),
                radius=CARD_RADIUS,
                fill=card_fill,
                outline=card_outline,
                width=2 if is_top3 else 0,
            )

            inner_x = PAD_X + 16
            row_center_y = y + (ROW_H - 6) // 2

            # ── Rank number ──
            rank_text = str(rank_num)
            if is_top3:
                rank_color = medal_border[rank_num]
            else:
                rank_color = TEXT_GRAY
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_rank)
            rank_w = rank_bbox[2] - rank_bbox[0]
            rank_h = rank_bbox[3] - rank_bbox[1]
            rank_x = inner_x
            rank_y = row_center_y - rank_h // 2 - 4
            draw.text((rank_x, rank_y), rank_text, font=font_rank, fill=rank_color)

            # ── Avatar ──
            av_size = 56
            av_x = inner_x + 50
            av_y = row_center_y - av_size // 2 - 4
            av = _rounded_avatar(avatar_raw, av_size)

            # Vòng tròn viền avatar cho top 3
            if is_top3:
                border_color = medal_border[rank_num]
                border_r = av_size // 2 + 3
                border_cx = av_x + av_size // 2
                border_cy = av_y + av_size // 2
                draw.ellipse(
                    (border_cx - border_r, border_cy - border_r,
                     border_cx + border_r, border_cy + border_r),
                    fill=border_color,
                )

            img.paste(av, (av_x, av_y), av)

            # ── Tên ──
            name_x = av_x + av_size + 16
            name_trunc = _truncate(name, 20)
            draw.text((name_x, row_center_y - 22), name_trunc, font=font_name, fill=TEXT_WHITE)

            # ── XP ──
            xp_text = f"{total_xp:,} XP"
            draw.text((name_x, row_center_y + 6), xp_text, font=font_xp, fill=TEXT_XP)

            # ── Thanh XP ──
            bar_w = 140
            bar_h = 10
            bar_x = width - PAD_X - 16 - bar_w
            bar_y = row_center_y - bar_h // 2 + 8

            _draw_rounded_rect(
                draw,
                (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
                radius=bar_h // 2,
                fill=BAR_BG,
            )

            fill_w = int(bar_w * max(0.0, min(ratio, 1.0)))
            if fill_w > 2:
                bar_color = medal_bar.get(rank_num, BAR_FILL)
                _draw_rounded_rect(
                    draw,
                    (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
                    radius=bar_h // 2,
                    fill=bar_color,
                )

        # ── Xuất PNG ──
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
