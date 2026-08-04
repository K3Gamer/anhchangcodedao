"""Tạo transcript HTML cho ticket từ lịch sử tin nhắn."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import discord

from utils.text import escape

_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcript - {channel_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background:#36393f; color:#dcddde; max-width:900px; margin:0 auto; padding:20px; }}
h1 {{ color:#ffffff; font-size:1.4rem; }}
.meta {{ color:#9a9fa5; font-size:0.85rem; margin-bottom:20px; }}
.message {{ display:flex; gap:12px; padding:10px 0; border-bottom:1px solid #2f3136; }}
.avatar {{ width:44px; height:44px; border-radius:50%; flex-shrink:0; }}
.author {{ color:#fff; font-weight:600; }}
.time {{ color:#9a9fa5; font-size:0.8rem; margin-left:8px; }}
.badge {{ margin-left:8px; font-size:0.7rem; background:#5865f2; padding:2px 6px; border-radius:8px; }}
.content {{ margin-top:4px; word-break:break-word; }}
.embed {{ background:#2f3136; border-left:4px solid #5865f2; padding:8px; margin:6px 0; border-radius:4px; }}
.attach {{ margin:4px 0; }}
a {{ color:#00b0f4; }}
</style>
</head>
<body>
<h1>📜 Transcript: {channel_name}</h1>
<div class="meta">Thời gian xuất: {created_at}<br>Lý do đóng: {reason}</div>
{messages}
</body>
</html>"""


def _build_html(
    channel: discord.TextChannel, ticket: dict, messages: list[discord.Message], reason: str
) -> str:
    """Dựng nội dung HTML từ danh sách tin nhắn."""
    owner_id = ticket.get("user_id")
    rows: list[str] = []

    for message in messages:
        author = escape(message.author.display_name)
        avatar = message.author.display_avatar.url
        time_str = discord.utils.format_dt(message.created_at, "f")

        parts: list[str] = []
        if message.content:
            parts.append(f'<div class="content">{escape(message.content)}</div>')
        for embed in message.embeds[:5]:
            title = escape(embed.title or "Embed")
            body = escape(embed.description or "")
            parts.append(f'<div class="embed"><b>{title}</b><br>{body}</div>')
        for attachment in message.attachments:
            parts.append(
                f'<div class="attach">📎 <a href="{attachment.url}">{escape(attachment.filename)}</a></div>'
            )
        body = "".join(parts) if parts else '<div class="content">(tin nhắn không có nội dung)</div>'

        badge = '<span class="badge">👑 Người tạo</span>' if message.author.id == owner_id else ""
        rows.append(
            f'<div class="message"><img class="avatar" src="{avatar}" alt="">'
            f'<div><div class="meta"><span class="author">{author}</span>'
            f'<span class="time">{time_str}</span>{badge}</div>{body}</div></div>'
        )

    return _TEMPLATE.format(
        channel_name=escape(channel.name),
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        reason=escape(reason or "Không có lý do"),
        messages="\n".join(rows) if rows else "<p>Không có tin nhắn nào trong ticket.</p>",
    )


async def generate_transcript(
    bot, channel: discord.TextChannel, ticket: dict, reason: str
) -> Path:
    """Tạo file HTML transcript từ lịch sử tin nhắn của ticket, trả về đường dẫn file."""
    messages: list[discord.Message] = [
        message async for message in channel.history(limit=None, oldest_first=True)
    ]
    html = _build_html(channel, ticket, messages, reason)

    folder = bot.data_dir / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{channel.name}-{int(time.time())}.html"
    path.write_text(html, encoding="utf-8")
    return path
