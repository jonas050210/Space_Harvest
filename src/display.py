"""Window / display helpers for the graphics settings menu.

Kept free of game logic so headless tests never import Ursina display code.
"""

from __future__ import annotations

from typing import Any


def parse_resolution(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return max(640, int(w)), max(480, int(h))
    except Exception:
        return 1440, 900


def apply_window_settings(settings: dict[str, Any]) -> None:
    """Push resolution / fullscreen / vsync / FOV into the live Ursina window.

    Safe no-op if Ursina is not imported or no window exists (headless).
    """
    try:
        from ursina import camera, window
    except Exception:
        return
    try:
        w, h = parse_resolution(str(settings.get("resolution", "1440x900")))
        window.size = (w, h)
    except Exception:
        pass
    try:
        window.fullscreen = bool(settings.get("fullscreen", False))
    except Exception:
        pass
    try:
        # Panda3D vsync: 1 on, 0 off. Ursina surfaces it as window.vsync on 8.x.
        vsync = bool(settings.get("vsync", True))
        if hasattr(window, "vsync"):
            window.vsync = vsync
        else:
            try:
                from panda3d.core import loadPrcFileData
                loadPrcFileData("", f"sync-video {'true' if vsync else 'false'}")
            except Exception:
                pass
    except Exception:
        pass
    try:
        camera.fov = float(settings.get("fov", 55))
    except Exception:
        pass
    # MSAA is a quality-preset concern; apply if the window exposes it.
    try:
        from src.config import QUALITY_PRESETS
        preset = QUALITY_PRESETS.get(settings.get("quality", "medium"), {})
        msaa = int(preset.get("msaa", 0) or 0)
        if hasattr(window, "render_mode") is False and hasattr(window, "msaa"):
            window.msaa = msaa
    except Exception:
        pass


def volume_from_settings(settings: dict[str, Any]) -> float:
    if settings.get("muted"):
        return 0.0
    try:
        return max(0.0, min(1.0, float(settings.get("master_volume", 0.75))))
    except Exception:
        return 0.75
