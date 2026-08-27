"""Project-relative path resolution.

No absolute platform paths are hard-coded. All writable locations derive
from the project root (or from the ``AI_VISION_LAB_DATA_DIR`` environment
variable, which tests use to redirect data/logs into a temp directory).

Production robustness: when the project directory is not writable (e.g.
a frozen EXE extracted into a protected location like ``Program Files``),
the data/logs directories transparently fall back to a per-user home
directory (``~/.ai-vision-lab``). Settings/models/logs keep working
either way.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_log = logging.getLogger("ai_vision_lab.paths")


def _home_fallback() -> Path:
    """Per-user fallback root (computed lazily, testable)."""
    return Path.home() / ".ai-vision-lab"


def _is_writable(directory: Path) -> bool:
    """True when the directory can be created and written to."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """Directory for settings and models; created on demand.

    Falls back to ``~/.ai-vision-lab/data`` when the project location is
    not writable (frozen EXE in a protected folder).
    """
    base = os.environ.get("AI_VISION_LAB_DATA_DIR")
    if base:
        directory = Path(base)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    candidate = PROJECT_ROOT / "data"
    if _is_writable(candidate):
        return candidate
    fallback = _home_fallback() / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    _log.warning(
        "Project data directory %s is not writable — using %s",
        candidate, fallback,
    )
    return fallback


def logs_dir() -> Path:
    """Directory for rotating log files; created on demand."""
    base = os.environ.get("AI_VISION_LAB_DATA_DIR")
    if base:
        directory = Path(base) / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    candidate = PROJECT_ROOT / "logs"
    if _is_writable(candidate):
        return candidate
    fallback = _home_fallback() / "logs"
    fallback.mkdir(parents=True, exist_ok=True)
    _log.warning(
        "Project logs directory %s is not writable — using %s",
        candidate, fallback,
    )
    return fallback


def models_dir() -> Path:
    """Directory for vision model files (.task / .tflite); created on demand."""
    directory = data_dir() / "models"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def recordings_dir() -> Path:
    """Directory for local video recordings and still snapshots."""
    directory = data_dir() / "recordings"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def extensions_dir() -> Path:
    """Directory for opt-in local plugins (``*.py``)."""
    directory = data_dir() / "extensions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def settings_path() -> Path:
    """Path of the JSON settings file."""
    return data_dir() / "settings.json"
