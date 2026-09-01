"""Ghi lại lỗi khởi động nghiêm trọng ra file để dễ chẩn đoán.

Console của panel hosting (Pterodactyl) hay bị cắt mất phần traceback.
Helper này chép toàn bộ traceback vào file logs/startup_error.log
để luôn nắm được lỗi thật dù console có bị cắt.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def log_fatal_to_file(extra_ctx: str = "") -> None:
    """Ghi traceback của exception đang xử lý vào file logs/startup_error.log."""
    path = Path(__file__).resolve().parent.parent / "logs" / "startup_error.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        exc = traceback.format_exc()
        stamp = datetime.now(timezone.utc).isoformat()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n{'=' * 60}\n[{stamp}] {extra_ctx}\n{'=' * 60}\n")
            fh.write(exc)
            fh.write("\n")
    except Exception:
        pass


def excepthook(exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001
    """Ghi lỗi chưa bắt qua sys.excepthook rồi in như bình thường."""
    traceback.print_exception(exc_type, exc_value, exc_tb)
    log_fatal_to_file("hoặc_đã_dừng_đột_ngột")


def install() -> None:
    """Gắn sys.excepthook để chắc chắn bắt được lỗi ở top-level."""
    sys.excepthook = excepthook


if __name__ == "__main__":  # pragma: no cover
    pass
