"""Minimal settings bridge kept for colony-state compatibility.

The orbital shell owns real settings in ``saves/_settings.json`` via
``src.main.Game``. This module supplies defaults that ``state.initial_state``
reads, and attempts to load the real settings file when present so headless
and tests see the same defaults as windowed.
"""

from __future__ import annotations

import json
import os

from . import config

DEFAULTS = {
    "language": "en",
    "difficulty": getattr(config, "DEFAULT_DIFFICULTY", "medium"),
    "music_on": True,
    "volume": 0.8,
    "last_save": None,
    "window_size": [1440, 900],
}


def _settings_path() -> str | None:
    try:
        from src.steam_bridge import cloud_root
        return os.path.join(cloud_root(), "_settings.json")
    except Exception:
        return None


def load() -> dict:
    defaults = DEFAULTS.copy()
    path = _settings_path()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                # Merge only known keys to avoid leaking unrelated data
                for k, v in data.items():
                    defaults[k] = v
                # The file may wrap in {"state": {...}} from old savegame impl
                if "state" in data and isinstance(data["state"], dict):
                    for k, v in data["state"].items():
                        defaults[k] = v
        except Exception:
            pass
    return defaults


def save(_data: dict) -> None:
    # Real persistence lives in Game.save_settings() / colony.savegame
    # This stub stays no-op for backward compat.
    return None
