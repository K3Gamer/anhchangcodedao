"""Nghiệp vụ Codeforces: gọi API contest.list, kiểm tra & gửi thông báo cho server."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp
import discord

from database.codeforces import REMIND_BEFORE, CodeforcesRepository
from utils.embeds import GREEN, ORANGE
from utils.time import format_duration

logger = logging.getLogger("codi")

API_URL = "https://codeforces.com/api/contest.list"
USER_AGENT = "CodiBot/1.0 (Discord notification)"
FETCH_TIMEOUT = 15
MAX_UPCOMING = 20

# Logo Codeforces (dùng làm thumbnail trong embed)
CF_LOGO_URL = "https://codeforces.com/codeforces.org/s/49829/images/codeforces-telegram-square-1024x1024.png"


class CodeforcesService:
    """Lấy danh sách kỳ thi sắp tới và gửi thông báo tới các server đã kích hoạt."""

    def __init__(self, bot: Any, repository: CodeforcesRepository) -> None:
        self.bot = bot
        self.repo = repository

    # ---------------------------------------------------------------
    # Lấy dữ liệu từ API Codeforces
    # ---------------------------------------------------------------
    async def fetch_upcoming(self) -> list[dict[str, Any]]:
        """Trả về danh sách kỳ thi đang ở phase 'BEFORE', sắp theo giờ bắt đầu."""
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, headers={"User-Agent": USER_AGENT}) as resp:
                data = await resp.json(content_type=None)
        if data.get("status") != "OK":
            raise RuntimeError(f"Codeforces API trả về trạng thái lạ: {data.get('status')}")
        contests = [c for c in data.get("result", []) if c.get("phase") == "BEFORE"]
        contests.sort(key=lambda c: c.get("startTimeSeconds", 0))
        return contests[:MAX_UPCOMING]

    # ---------------------------------------------------------------
    # Vòng kiểm tra định kỳ
    # ---------------------------------------------------------------
    async def check(self) -> None:
        """Quét kỳ thi mới / sắp diễn ra rồi gửi thông báo cho từng server đã bật."""
        try:
            contests = await self.fetch_upcoming()
        except Exception as exc:
            logger.warning("Không lấy được danh sách kỳ thi Codeforces: %s", exc)
            return

        current_ids = {int(c["id"]) for c in contests}

        for doc in await self.repo.get_enabled():
            await self._process_guild(doc, contests, current_ids)

    async def _process_guild(
        self,
        doc: dict[str, Any],
        contests: list[dict[str, Any]],
        current_ids: set[int],
    ) -> None:
        guild_id = int(doc.get("_id"))
        channel_id = doc.get("channel_id")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "Bỏ qua thông báo CF: kênh %s của guild %s không hợp lệ", channel_id, guild_id
            )
            return

        notified = doc.get("notified", {})
        stale = [cid for cid in notified if int(cid) not in current_ids]
        if stale:
            for cid in stale:
                notified.pop(cid, None)
            await self.repo.update(guild_id, {"notified": notified})

        ping = f"<@&{doc.get('ping_role_id')}>" if doc.get("ping_role_id") else None

        for contest in contests:
            try:
                await self._handle_contest(guild_id, channel, contest, notified, ping)
            except Exception:
                logger.exception(
                    "Lỗi xử lý thông báo CF contest %s cho guild %s",
                    contest.get("id"),
                    guild_id,
                )

    async def _handle_contest(
        self,
        guild_id: int,
        channel: discord.TextChannel,
        contest: dict[str, Any],
        notified: dict[str, Any],
        ping: str | None,
    ) -> None:
        contest_id = int(contest["id"])
        start = datetime.fromtimestamp(contest["startTimeSeconds"], tz=timezone.utc)
        remaining = (start - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return

        entry = notified.get(str(contest_id)) or {}
        announced = bool(entry.get("announced"))
        reminded = bool(entry.get("reminded"))

        if not announced:
            embed = self.build_contest_embed(contest, soon=False)
            await self._send(channel, embed, ping)
            await self.repo.set_notified(guild_id, contest_id, "announced", True)
            announced = True

        if not reminded and remaining <= REMIND_BEFORE:
            embed = self.build_contest_embed(contest, soon=True)
            await self._send(channel, embed, ping)
            await self.repo.set_notified(guild_id, contest_id, "reminded", True)

    # ---------------------------------------------------------------
    # Gửi tin nhắn
    # ---------------------------------------------------------------
    @staticmethod
    async def _send(channel: discord.TextChannel, embed: discord.Embed, ping: str | None) -> None:
        try:
            await channel.send(content=ping, embed=embed)
        except discord.HTTPException:
            logger.warning("Không gửi được thông báo CF vào kênh %s", channel.id)

    # ---------------------------------------------------------------
    # Tạo Embed
    # ---------------------------------------------------------------
    def build_contest_embed(self, contest: dict[str, Any], *, soon: bool) -> discord.Embed:
        """Embed thông báo một kỳ thi (kỳ thi mới hoặc sắp bắt đầu)."""
        start = datetime.fromtimestamp(contest["startTimeSeconds"], tz=timezone.utc)
        link = f"https://codeforces.com/contestRegistration/{contest['id']}"
        if soon:
            embed = self.bot.embeds.base(
                title="⚡ Kỳ thi Codeforces sắp bắt đầu!",
                description=contest.get("name"),
                color=ORANGE,
            )
        else:
            embed = self.bot.embeds.base(
                title="📢 Kỳ thi Codeforces mới",
                description=contest.get("name"),
                color=GREEN,
            )
        embed.add_field(name="🕒 Bắt đầu", value=discord.utils.format_dt(start, "F"))
        embed.add_field(name="⏳ Còn lại", value=discord.utils.format_dt(start, "R"))
        embed.add_field(name="📅 Thời lượng", value=format_duration(contest.get("durationSeconds", 0)))
        embed.add_field(name="🏆 Loại", value=str(contest.get("type") or "CF"))
        embed.add_field(name="🔗 Đăng ký", value=f"[Nhấn để đăng ký]({link})", inline=False)
        return embed

    async def get_next(self) -> dict[str, Any] | None:
        """Kỳ thi gần nhất sắp diễn ra (None nếu không có)."""
        competitions = await self.fetch_upcoming()
        return competitions[0] if competitions else None

    @staticmethod
    def parse_rules(name: str) -> str:
        """Tách 'Round X • Div. Y' từ tên kỳ thi (vd 'Codeforces Round 1122 (Div. 3)')."""
        if not name:
            return "Codeforces Round"
        lower = name.lower()
        if "educational" in lower:
            label = "Educational Round"
        elif "global" in lower:
            label = "Global Round"
        else:
            label = "Codeforces Round"

        round_match = re.search(r"round\s*#?\s*(\d+)", lower)
        round_no = round_match.group(1) if round_match else ""

        divs = sorted(set(re.findall(r"div\.?\s*(\d)", lower)))
        div_text = f" • Div. {' & '.join(divs)}" if divs else ""

        return f"{label} {round_no}{div_text}".strip()

    def build_fcontest_embed(self, contest: dict[str, Any]) -> discord.Embed:
        """Embed `/cf fcontest`: logo Codeforces + giờ thi + còn bao nhiêu + nút tham gia."""
        start = datetime.fromtimestamp(contest["startTimeSeconds"], tz=timezone.utc)
        rules = self.parse_rules(contest.get("name", ""))
        link = f"https://codeforces.com/contestRegistration/{contest['id']}"

        embed = self.bot.embeds.base(
            title=f"🏆 {rules}",
            description=contest.get("name"),
        )
        embed.set_thumbnail(url=CF_LOGO_URL)
        embed.add_field(name="🕒 Thời gian bắt đầu", value=discord.utils.format_dt(start, "F"))
        embed.add_field(name="⏳ Còn lại", value=discord.utils.format_dt(start, "R"))
        embed.add_field(name="📅 Thời lượng", value=format_duration(contest.get("durationSeconds", 0)))
        embed.add_field(name="🏆 Loại", value=str(contest.get("type") or "CF"))
        embed.add_field(name="🔗 Đăng ký", value=f"[Codeforces Round {contest['id']}]({link})", inline=False)
        return embed

    async def build_upcoming_embed(self) -> tuple[discord.Embed | None, list[dict[str, Any]]]:
        """Embed danh sách kỳ thi sắp tới (trả None nếu không có kỳ thi nào)."""
        try:
            contests = await self.fetch_upcoming()
        except Exception as exc:
            logger.warning("Không lấy được danh sách kỳ thi Codeforces: %s", exc)
            return None, []

        if not contests:
            return None, []

        lines: list[str] = []
        for contest in contests:
            start = datetime.fromtimestamp(contest["startTimeSeconds"], tz=timezone.utc)
            link = f"https://codeforces.com/contestRegistration/{contest['id']}"
            lines.append(
                f"**{contest.get('name')}**\n"
                f"🕒 {discord.utils.format_dt(start, 'F')} • "
                f"⏳ {discord.utils.format_dt(start, 'R')} • "
                f"⏱️ {format_duration(contest.get('durationSeconds', 0))}\n"
                f"🔗 [{link}]({link})"
            )

        embed = self.bot.embeds.base(
            title=f"📅 Kỳ thi Codeforces sắp diễn ra ({len(contests)})",
            description="\n\n".join(lines),
        )
        return embed, contests

    async def seed(self, guild_id: int) -> None:
        """Đánh dấu các kỳ thi hiện tại là 'đã thông báo' để không gửi trùng lên lịch sử.

        Chỉ thông báo những kỳ thi MỚI xuất hiện từ sau khi server bật tính năng.
        """
        try:
            contests = await self.fetch_upcoming()
        except Exception:
            return
        for contest in contests:
            await self.repo.set_notified(guild_id, int(contest["id"]), "announced", True)