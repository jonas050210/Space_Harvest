"""Logging setup.

All loggers are children of the ``ai_vision_lab`` root logger. Output goes
to a rotating file (``logs/vision_lab.log``) and to stdout. The setup
function is idempotent, so tests and the application can call it safely.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "ai_vision_lab"

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3


def setup_logging(logs_dir: Path, debug: bool = False) -> None:
    """(Re-)configure the root application logger.

    Existing handlers are replaced, so the function can safely be called
    more than once (e.g. after a data-directory change or in tests).

    Args:
        logs_dir: Directory that receives ``vision_lab.log``.
        debug: Enable DEBUG level (default: INFO).
    """
    root = logging.getLogger(LOGGER_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except OSError:
            pass

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.propagate = False
    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            logs_dir / "vision_lab.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Logging must never crash the app (e.g. read-only filesystem).
        root.warning("Could not create log file in %s", logs_dir)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def set_debug(enabled: bool) -> None:
    """Switch the root logger between DEBUG and INFO at runtime."""
    logging.getLogger(LOGGER_NAME).setLevel(logging.DEBUG if enabled else logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the application root."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
