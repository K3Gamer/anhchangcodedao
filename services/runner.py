"""Điều khiển GitHub Actions để khởi động lại bot (dùng cho lệnh /restart).

Bot được host trong workflow "Host Bot" (.github/workflows/bot.yml) chạy tối đa
~6h/lần. Muốn chạy lại bot ngay thì phải tạo một workflow run mới rồi hủy run
đang chạy (vì `concurrency` của workflow không cho chạy song song 2 job bot).

Thứ tự bắt buộc: đẩy dữ liệu -> dispatch run mới -> hủy run hiện tại. Nếu hủy
trước rồi mới dispatch, run mới sẽ không bao giờ được tạo.
"""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

from core.config import BASE_DIR
from core.errors import BotError

logger = logging.getLogger("codi")

# File workflow chứa job bot (không phải tên hiển thị "Host Bot")
WORKFLOW_FILE = "bot.yml"

# Giới hạn chờ khi đẩy dữ liệu lên nhánh `data`
PUSH_DATA_TIMEOUT = 120.0

API_ROOT = "https://api.github.com"


class RunnerService:
    """Dispatch / hủy workflow run của GitHub Actions.

    Chỉ hoạt động khi bot đang chạy trong GitHub Actions (có GITHUB_TOKEN và
    GITHUB_REPOSITORY). Khi chạy local, `available` là False.
    """

    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN", "").strip()
        self.repo = os.getenv("GITHUB_REPOSITORY", "").strip()
        self.run_id = os.getenv("GITHUB_RUN_ID", "").strip()
        self.ref = os.getenv("GITHUB_REF_NAME", "").strip() or "main"

    @property
    def available(self) -> bool:
        """Có đủ thông tin để gọi API GitHub không."""
        return bool(self.token and self.repo)

    @property
    def actions_url(self) -> str:
        """Link trang Actions để người dùng theo dõi lần chạy mới."""
        return f"https://github.com/{self.repo}/actions" if self.repo else ""

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Đẩy dữ liệu
    # ------------------------------------------------------------------
    async def push_data(self) -> str:
        """Đẩy ./data lên nhánh `data` để không mất XP/config khi bot bị giết."""
        script = BASE_DIR / ".github" / "scripts" / "push_data.sh"
        if not script.is_file():
            raise BotError(f"Không tìm thấy script đẩy dữ liệu: {script}")

        proc = await asyncio.create_subprocess_exec(
            "bash",
            str(script),
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=PUSH_DATA_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise BotError(
                f"Đẩy dữ liệu quá {PUSH_DATA_TIMEOUT:.0f}s, đã huỷ để tránh treo bot."
            ) from None

        output = (stdout or b"").decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            tail = "\n".join(output.splitlines()[-3:])
            logger.error("push_data.sh thất bại (code %s):\n%s", proc.returncode, output)
            raise BotError(f"Không đẩy được dữ liệu lên nhánh `data`:\n```{tail}```")

        return output or "Đã đẩy dữ liệu (không có thay đổi)."

    # ------------------------------------------------------------------
    # Dispatch / hủy workflow run
    # ------------------------------------------------------------------
    async def dispatch(self, ref: str | None = None) -> None:
        """Tạo một workflow run mới. Chạy được vì workflow_dispatch là ngoại lệ
        của quy tắc chặn tạo run đệ quy bằng GITHUB_TOKEN."""
        url = f"{API_ROOT}/repos/{self.repo}/actions/workflows/{WORKFLOW_FILE}/dispatches"
        payload = {"ref": ref or self.ref}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._headers(self.token), json=payload
            ) as resp:
                if resp.status != 204:
                    body = (await resp.text())[:300]
                    logger.error("dispatch workflow thất bại: HTTP %s %s", resp.status, body)
                    raise BotError(f"GitHub từ chối tạo run mới (HTTP {resp.status}): {body}")

    async def cancel_current_run(self) -> bool:
        """Huỷ workflow run đang chứa tiến trình bot này."""
        if not self.run_id:
            logger.warning("Không có GITHUB_RUN_ID, bỏ qua bước huỷ run hiện tại.")
            return False

        url = f"{API_ROOT}/repos/{self.repo}/actions/runs/{self.run_id}/cancel"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._headers(self.token)) as resp:
                if resp.status not in (200, 202):
                    body = (await resp.text())[:300]
                    logger.error("huỷ run thất bại: HTTP %s %s", resp.status, body)
                    raise BotError(f"Không huỷ được run hiện tại (HTTP {resp.status}): {body}")
        return True