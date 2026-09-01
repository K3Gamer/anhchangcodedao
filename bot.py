"""Điểm khởi động chính của bot "Codi"."""

from __future__ import annotations

import asyncio
import logging

from core.bot import CodiBot
from core.config import load_config
from core.database import Database
from core.logging import setup_logging
from database.guild_config import GuildConfigManager
from services.leveling import LevelingService

logger = logging.getLogger("codi")


async def main() -> None:
    """Khởi tạo storage dữ liệu rồi chạy bot."""
    cfg = load_config()

    if not cfg.token:
        logger.critical(
            "Chưa cấu hình DISCORD_TOKEN. Vui lòng tạo file .env theo hướng dẫn trong .env.example"
        )
        return

    try:
        await Database.connect()
    except Exception as exc:
        logger.critical("Không thể khởi tạo storage dữ liệu (%s). Kiểm tra thư mục data/.", exc)
        return

    bot = CodiBot()
    bot.db = Database.get_db()
    bot.config_manager = GuildConfigManager(bot.db)
    bot.leveling_service = LevelingService(bot.db)

    try:
        await bot.start(cfg.token, reconnect=True)
    except KeyboardInterrupt:
        logger.info("Bot đã bị dừng bởi người dùng.")
    finally:
        await Database.close()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot đã bị dừng bởi người dùng.")
    except Exception as exc:
        logger.critical("Bot gặp lỗi nghiêm trọng: %s", exc, exc_info=True)
