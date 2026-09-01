"""Sinh ảnh bảng xếp hạng hiện đại với Pillow.

Thiết kế: nền gradient Blurple, card trong suốt bo góc, avatar tròn,
thanh XP gradient, top 3 được tô màu vàng/bạc/đồng, cột thứ hạng lớn.
"""

from __future__ import annotations

import asyncio
import io
import os
import platform

import aiohttp
from PIL import Image, ImageDraw, ImageFont

# Bảng màu
BG_TOP = (31, 38, 74)         # đậm
BG_BOTTOM = (88, 101, 242)    # Blurple sáng
CARD_BG = (255, 255, 255, 40)  # card trắng trong suốt
CARD_BG_SOLID = (44, 50, 95)
TEXT_MAIN = (255, 255, 255)
TEXT_DIM = (190, 198, 235)
BAR_BG = (255, 255, 255, 45)
BAR_FILL_A = (255, 214, 102)
BAR_FILL_B = (255, 145, 77)

MEDAL = {
    1: (255, 215, 64),
    2: (196, 202, 217),
    3: (205, 138, 61),
}

ROW_H = 96
PAD = 40


def _rounded_avatar(img: Image.Image, size: int, radius: int) -> Image.Image:
    """Cắt ảnh vuông bo tròn hoàn toàn (hình tròn)."""
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


async def _fetch_avatar(session: aiohttp.ClientSession, url: str) -> Image.Image:
    """Tải avatar; fallback về hình tròn mặc định nếu lỗi."""
    default = Image.new("RGBA", (256, 256), (58, 65, 110, 255))
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return default
            data = await resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        return img
    except Exception:
        return default


def _font_candidates(weight: str) -> list[tuple[str, str]]:
    """Danh sách (tên file, tên đầy đủ) font theo độ ưu tiên cho từng OS.

    Ưu tiên font hỗ trợ tiếng Việt có dấu. DejaVuSans có sẵn trên mọi Linux.
    """
    if weight == "bold":
        return [
            ("DejaVuSans-Bold.ttf", "DejaVuSans-Bold"),
            ("arialbd.ttf", "Arial Bold"),
            ("Arial-Bold.ttf", "Arial Bold"),
            ("segoeuib.ttf", "Segoe UI Bold"),
            ("LiberationSans-Bold.ttf", "LiberationSans-Bold"),
            ("NotoSans-Bold.ttf", "NotoSans-Bold"),
        ]
    return [
        ("DejaVuSans.ttf", "DejaVuSans"),
        ("arial.ttf", "Arial"),
        ("Arial.ttf", "Arial"),
        ("segoeui.ttf", "Segoe UI"),
        ("LiberationSans-Regular.ttf", "LiberationSans"),
        ("NotoSans-Regular.ttf", "NotoSans"),
        ("Arimo-Regular.ttf", "Arimo"),
    ]


def _font_dirs() -> list[str]:
    """Các thư mục chứa font hệ thống theo nền tảng (thử hết, bỏ trùng)."""
    system = platform.system()
    dirs: list[str] = []
    if system == "Darwin":
        dirs += [
            "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
            "/Library/Fonts",
        ]
    dirs += [
        "C:\\Windows\\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/truetype/arimo",
        "/usr/local/share/fonts",
        "/usr/share/fonts",
    ]
    return list(dict.fromkeys(dirs))


def _load_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font hệ thống hỗ trợ tiếng Việt; fallback về font mặc định của Pillow."""
    search = _font_dirs()
    for fname, _ in _font_candidates(weight):
        for d in search:
            p = os.path.join(d, fname)
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    # Fallback: font mặc định (nhỏ nhất định)
    return ImageFont.load_default()


class LeaderboardRenderer:
    """Nạp & vẽ ảnh leaderboard."""

    async def render(
        self,
        entries: list[tuple[str, str, int, float]],
        top: int = 3,
        title: str = "Bảng xếp hạng XP",
    ) -> bytes:
        """entries: list[(avatar_url, nickname, total_xp, progress_ratio)].Trả về bytes PNG."""
        font_title = _load_font(46, "bold")
        font_sub = _load_font(22)
        font_rank_big = _load_font(40, "bold")
        font_name = _load_font(26, "bold")
        font_medal = _load_font(34, "bold")
        font_xp = _load_font(20)
        font_pos = _load_font(20)

        n = len(entries)
        width = 1100
        header = 170
        height = header + n * ROW_H + PAD

        # Gradient nền
        img = Image.new("RGB", (width, height), BG_TOP)
        draw = ImageDraw.Draw(img)
        for y in range(height):
            t = y / height
            r = int(round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t))
            g = int(round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t))
            b = int(round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t))
            draw.line((0, y, width, y), fill=(r, g, b))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rounded_rectangle((0, 0, width, height), radius=28, fill=(0, 0, 0, 60))
        img = Image.alpha_composite(img.convert("RGBA"), overlay)

        draw = ImageDraw.Draw(img)

        # Tiêu đề
        draw.text((PAD, 34), title, font=font_title, fill=TEXT_MAIN)
        draw.text((PAD, 98), f"Tổng cộng {n} thành viên · Cập nhật mỗi tin nhắn",
                  font=font_sub, fill=TEXT_DIM)

        async with aiohttp.ClientSession() as session:
            avatars = await asyncio.gather(
                *[_fetch_avatar(session, url) for url, _, _, _ in entries]
            )

            for i, ((url, name, total_xp, ratio), avatar_raw) in enumerate(zip(entries, avatars)):
                y = header + i * ROW_H
                top3 = i < top
                row_top = i + 1

                # Card nền
                if top3:
                    medal_color = MEDAL[row_top]
                    draw.rounded_rectangle(
                        (PAD, y + 8, width - PAD, y + ROW_H + 8),
                        radius=18, fill=(*medal_color, 36), outline=(*medal_color, 255), width=3,
                    )
                else:
                    draw.rounded_rectangle(
                        (PAD, y + 8, width - PAD, y + ROW_H + 8),
                        radius=18, fill=CARD_BG, width=0,
                    )

                # Avatar
                av_size = 64
                av = _rounded_avatar(avatar_raw, av_size, av_size // 2)
                img.paste(av, (PAD + 18, y + 8 + (ROW_H - av_size) // 2), av)
                av_center_x = PAD + 18 + av_size // 2

                # Thứ hạng
                rank_x = av_center_x + 46
                if top3:
                    draw.text((rank_x + 12, y + 30), str(row_top), font=font_rank_big,
                              fill=medal_color)
                else:
                    draw.text((rank_x + 14, y + 30), str(row_top), font=font_rank_big,
                              fill=TEXT_DIM)

                # Tên + XP
                name_x = rank_x + 58
                draw.text((name_x, y + 26), _truncate(name, 26), font=font_name, fill=TEXT_MAIN)
                draw.text((name_x, y + 58), f"{total_xp:,} XP", font=font_xp, fill=TEXT_DIM)

                # Thanh XP bên phải
                bar_w = 300
                bar_h = 14
                bar_x = width - PAD - bar_w - 24
                bar_y = y + (ROW_H - bar_h) // 2 + 16
                draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
                                       radius=bar_h // 2, fill=BAR_BG)
                # XP hiện tại trong level (tỉ lệ thật truyền vào)
                fill_w = int(bar_w * max(0.0, min(ratio, 1.0)))
                if fill_w > bar_h:
                    draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
                                           radius=bar_h // 2, fill=BAR_FILL_A)
                # Top 3 huy chương (vòng tròn màu vàng/bạc/đồng)
                if top3:
                    mc = bar_x + bar_w + 16
                    mcy = bar_y + bar_h // 2
                    mr = 15
                    draw.ellipse((mc - mr, mcy - mr, mc + mr, mcy + mr), fill=medal_color)
                    # số thứ hạng trong huy chương
                    t = str(row_top)
                    bbox = draw.textbbox((0, 0), t, font=font_medal)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                    draw.text((mc - tw / 2, mcy - th / 2), t, font=font_medal, fill=(31, 38, 74))

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()


def _truncate(text: str, max_len: int) -> str:
    """Cắt dài tên, thêm '…' nếu vượt giới hạn."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
