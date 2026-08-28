"""JSON save and load. Slots live in the Steam-cloud-friendly save root."""

from __future__ import annotations

import json
import os
import time

# Meta files that are not campaign slots.
META_FILES = ("_settings.json", "achievements_progress.json", "steam_stats.json")


def _default_save_dir() -> str:
    try:
        from src.steam_bridge import cloud_root

        return cloud_root()
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "saves")
        os.makedirs(path, exist_ok=True)
        return path


SAVE_DIR = _default_save_dir()


def ensure_dir() -> None:
    if not os.path.isdir(SAVE_DIR):
        os.makedirs(SAVE_DIR)


def list_saves() -> list[str]:
    """Campaign slot filenames, newest first. Settings / Steam meta omitted."""
    ensure_dir()
    files = []
    for name in os.listdir(SAVE_DIR):
        if not name.endswith(".json") or name in META_FILES:
            continue
        files.append(name)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_DIR, x)), reverse=True)
    return files


def save_slot(name: str, state_dict) -> str:
    ensure_dir()
    path = os.path.join(SAVE_DIR, f"{name}.json")
    data = {
        "timestamp": time.time(),
        "name": name,
        "state": state_dict,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return path


def load_slot(name: str):
    path = os.path.join(SAVE_DIR, f"{name}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("state", {})
