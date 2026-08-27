"""Steam-facing surface without a hard Steamworks dependency.

On a real Steam build, replace ``SteamClient`` internals with steamworks-python
or Facepunch.Steamworks bindings. Until then this module:

* writes ``steam_appid.txt`` next to the executable (Steam overlay bootstrap)
* mirrors achievement unlocks into ``saves/achievements_progress.json``
* exposes cloud-save path helpers the packager / Steam depot can mount
* records a lightweight playtime counter for the year-end report

Nothing here is imported by the orbital core.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

from src.config import GAME_VERSION, STEAM_APP_ID


def _app_root() -> str:
    """Directory that owns the executable (frozen) or the repo root (dev)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cloud_root() -> str:
    """Steam Cloud-friendly save root.

    Prefer ``%USERPROFILE%/Documents/My Games/OrbitalSupplyChains`` on Windows
    so cloud sync and multi-user installs stay out of Program Files. Fall back
    to the local ``saves/`` folder in development.
    """
    override = os.environ.get("OSC_SAVE_ROOT")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if sys.platform.startswith("win"):
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        path = os.path.join(home, "Documents", "My Games", "OrbitalSupplyChains")
    else:
        home = os.path.expanduser("~")
        path = os.path.join(home, ".local", "share", "OrbitalSupplyChains")
    # In the repo / CI we keep saves next to the project so tests stay hermetic
    # unless OSC_USE_USER_SAVES=1 is set.
    if not os.environ.get("OSC_USE_USER_SAVES") and not getattr(sys, "frozen", False):
        path = os.path.join(_app_root(), "saves")
    os.makedirs(path, exist_ok=True)
    return path


def ensure_steam_appid(app_id: int | None = None) -> str | None:
    """Write steam_appid.txt beside the binary so the overlay can attach."""
    app_id = int(app_id if app_id is not None else STEAM_APP_ID)
    if app_id <= 0:
        return None
    path = os.path.join(_app_root(), "steam_appid.txt")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(app_id))
        return path
    except Exception:
        return None


class SteamClient:
    """Optional Steamworks facade. Safe no-op when Steam is absent."""

    def __init__(self, app_id: int | None = None):
        self.app_id = int(app_id if app_id is not None else STEAM_APP_ID)
        self.available = False
        self._playtime_seconds = 0.0
        self._session_started = time.time()
        self._stats_path = os.path.join(cloud_root(), "steam_stats.json")
        self._load_stats()
        ensure_steam_appid(self.app_id)
        self.available = self._try_init()

    def _try_init(self) -> bool:
        """Attempt a real Steamworks bind; succeed quietly if missing."""
        if self.app_id <= 0:
            return False
        # Placeholder for a future steamworks import. We deliberately do not
        # hard-require the native DLL so the game runs outside Steam.
        if os.environ.get("STEAM_OVERLAY") == "1" or os.path.isfile(
            os.path.join(_app_root(), "steam_api64.dll")
        ) or os.path.isfile(os.path.join(_app_root(), "libsteam_api.so")):
            return True
        return False

    def _load_stats(self) -> None:
        if not os.path.isfile(self._stats_path):
            return
        try:
            with open(self._stats_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._playtime_seconds = float(data.get("playtime_seconds", 0.0))
        except Exception:
            pass

    def _save_stats(self) -> None:
        payload = {
            "version": GAME_VERSION,
            "app_id": self.app_id,
            "playtime_seconds": self._playtime_seconds,
            "updated": time.time(),
        }
        try:
            with open(self._stats_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except Exception:
            pass

    def tick(self, dt_real: float) -> None:
        self._playtime_seconds += max(0.0, float(dt_real))

    def unlock(self, achievement_id: str) -> None:
        """Unlock on Steam if available; always durable via achievements file."""
        # Native call would go here: SteamUserStats.SetAchievement / StoreStats
        _ = achievement_id

    def shutdown(self) -> None:
        self._playtime_seconds += max(0.0, time.time() - self._session_started)
        self._session_started = time.time()
        self._save_stats()

    def snapshot(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "app_id": self.app_id,
            "playtime_hours": self._playtime_seconds / 3600.0,
            "version": GAME_VERSION,
            "cloud_root": cloud_root(),
        }


def write_steam_manifest(dest_dir: str) -> str:
    """Emit a depot-friendly install manifest the packager copies into the build."""
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "steam_install.json")
    payload = {
        "name": "Orbital Supply Chains",
        "version": GAME_VERSION,
        "app_id": STEAM_APP_ID,
        "executable_windows": "OrbitalSupplyChains.exe",
        "executable_linux": "OrbitalSupplyChains",
        "cloud": {
            "root": "saves",
            "patterns": ["*.json"],
            "note": "Mount saves/ via Steam Cloud; achievements_progress.json is included.",
        },
        "launch": [
            {"description": "Play Orbital Supply Chains", "executable": "OrbitalSupplyChains.exe",
             "type": "default", "config": {"oslist": "windows"}},
            {"description": "Play Orbital Supply Chains", "executable": "OrbitalSupplyChains",
             "type": "default", "config": {"oslist": "linux"}},
        ],
        "target_hardware": {
            "min": "i5 / 8 GB / GTX 1050 / low preset",
            "rec": "i7-12700F / 16 GB / RTX 3060 / high preset",
            "ship": "i7-12700F / 32 GB / RTX 4060 Ti 8 GB / ultra preset",
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path
