"""Entry point fallback cho fps.ms (mặc định chạy main.py) — ủy quyền cho bot.py."""

import asyncio

from bot import main
from core.logging import setup_logging
from utils.crash_log import install as install_crash_log, log_fatal_to_file

if __name__ == "__main__":
    install_crash_log()
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        log_fatal_to_file("main.py")
