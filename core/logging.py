"""Thiết lập logging: console + file (RotatingFileHandler)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core.config import load_config

# Tên logger dùng chung toàn bot
LOGGER_NAME = "anhchangcodedao"


def setup_logging() -> logging.Logger:
    """Cấu hình logger toàn cục. Idempotent — gọi nhiều lần vẫn an toàn."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    cfg = load_config()
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    logger.setLevel(getattr(logging, cfg.log_level, logging.INFO))

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler ghi toàn bộ log vào file bot.log (tối đa 5MB, giữ 5 bản)
    file_handler = RotatingFileHandler(
        cfg.log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # Handler riêng cho lỗi nghiêm trọng
    error_handler = RotatingFileHandler(
        cfg.log_dir / "error.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    # Handler in ra console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)

    return logger
