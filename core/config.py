"""Cấu hình ứng dụng đọc từ biến môi trường (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Đường dẫn gốc của dự án (tương đối, không ghi cứng đường dẫn tuyệt đối)
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    """Cấu hình toàn cục của bot."""

    token: str
    log_level: str
    log_dir: Path
    data_dir: Path

    @property
    def is_configured(self) -> bool:
        """Kiểm tra đã đủ token để chạy chưa."""
        return bool(self.token)


def load_config() -> Config:
    """Đọc & trả về cấu hình từ file .env (hoặc biến môi trường)."""
    return Config(
        token=os.getenv("DISCORD_TOKEN", "").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        log_dir=BASE_DIR / "logs",
        data_dir=BASE_DIR / "data",
    )
