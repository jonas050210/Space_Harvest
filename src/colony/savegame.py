"""JSON save and load. Slots live in the Steam-cloud-friendly save root."""

from __future__ import annotations

import json
import os
import sys
import time

# Meta files that are not campaign slots.
META_FILES = ("_settings.json", "achievements_progress.json", "steam_stats.json")


def _default_save_dir() -> str:
    """Resolve save dir lazily so env-var overrides work even after import."""
    try:
        from src.steam_bridge import cloud_root
        return cloud_root()
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(root, "saves")
        os.makedirs(p, exist_ok=True)
        return p


# Original value at import time - used to detect monkeypatch in tests
_ORIGINAL_SAVE_DIR = _default_save_dir()
SAVE_DIR = _ORIGINAL_SAVE_DIR


def get_save_dir() -> str:
    """Public accessor - fresh, respects env overrides and test monkeypatch."""
    # Env override has highest priority
    try:
        from src.steam_bridge import cloud_root
        # cloud_root itself checks env vars, so if env var is set it will differ
        # from _ORIGINAL_SAVE_DIR, but we still call it to get the env-aware path
        env_path = cloud_root()
        # If env var is set, cloud_root returns that env path - use it
        # Detect env var presence
        if os.environ.get("SPACE_HARVEST_SAVE_ROOT") or os.environ.get("OSC_SAVE_ROOT"):
            return env_path
    except Exception:
        pass

    # Check for monkeypatched SAVE_DIR (tests do monkeypatch.setattr(SAVE_DIR, tmp_path))
    mod = sys.modules.get(__name__)
    if mod is not None:
        try:
            current = mod.__dict__.get("SAVE_DIR")
            if current is not None and str(current) != str(_ORIGINAL_SAVE_DIR):
                # If it's been monkeypatched to a tmp_path or other location, respect it
                return str(current)
        except Exception:
            pass

    # Fallback to fresh default (handles cloud_root changes)
    return _default_save_dir()


def ensure_dir() -> None:
    d = get_save_dir()
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def list_saves() -> list[str]:
    """Campaign slot filenames, newest first. Settings / Steam meta omitted.

    Sorts by internal timestamp when readable, falls back to mtime.
    """
    ensure_dir()
    save_dir = get_save_dir()
    entries: list[tuple[float, str]] = []
    try:
        files = os.listdir(save_dir)
    except OSError:
        return []
    for name in files:
        if not name.endswith(".json") or name in META_FILES:
            continue
        full = os.path.join(save_dir, name)
        ts = 0.0
        try:
            with open(full, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ts = float(data.get("timestamp", 0.0) or 0.0)
        except Exception:
            pass
        if ts <= 0.0:
            try:
                ts = os.path.getmtime(full)
            except OSError:
                ts = 0.0
        entries.append((ts, name))
    entries.sort(key=lambda x: x[0], reverse=True)
    return [name for _ts, name in entries]


def save_slot(name: str, state_dict) -> str:
    """Write a slot atomically: dump to a temp file, then replace in place."""
    ensure_dir()
    save_dir = get_save_dir()
    path = os.path.join(save_dir, f"{name}.json")
    data = {
        "timestamp": time.time(),
        "name": name,
        "state": state_dict,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    if os.path.isfile(path):
        try:
            os.replace(path, f"{path}.bak")
        except OSError:
            pass
    os.replace(tmp, path)
    return path


def load_slot(name: str):
    """Load a slot; a corrupt or unreadable save returns None, never raises."""
    save_dir = get_save_dir()
    path = os.path.join(save_dir, f"{name}.json")
    for candidate in (path, f"{path}.bak"):
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data.get("state", {})
        except (OSError, ValueError):
            continue
    return None
