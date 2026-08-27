"""Minimal settings stub kept for the colony-state bridge.

The orbital shell owns real settings in ``saves/_settings.json`` via
``src.main.Game``. This module only supplies defaults that
``state.initial_state`` still reads.
"""

from __future__ import annotations

from . import config

DEFAULTS = {
    "language": "en",
    "difficulty": getattr(config, "DEFAULT_DIFFICULTY", "medium"),
    "music_on": True,
    "volume": 0.8,
    "last_save": None,
    "window_size": [1440, 900],
}


def load():
    return DEFAULTS.copy()


def save(_data):
    return None
