"""Entry point cho fps.ms (mặc định chạy app.py) — ủy quyền cho bot.py."""

import asyncio

from bot import main
from core.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
