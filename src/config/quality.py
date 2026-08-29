"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- quality presets -----------------------------------------------------------
# Flags feed OrbitalScene.apply_quality. Tuned for the target PC
# (i7-12700F / RTX 4060 Ti 8 GB): ultra is the showcase preset; low keeps
# Steam Deck / integrated fallback playable. medium is the default ship.
QUALITY_PRESETS = {
    "low": {
        "belt": False, "trails": False, "sky": True, "labels": True,
        "corona": False, "flares": False, "reticle": True, "orbit_alpha": 0.25,
        "belt_density": 0.0, "ship_lod": "simple", "msaa": 0, "vsync": True,
        "bloom": False, "shadows": False, "particles": False,
        "drones_fx": False, "surface_detail": False, "map_grid": True,
        "star_twinkle": False, "atmosphere": False,
    },
    "medium": {
        "belt": True, "trails": True, "sky": True, "labels": True,
        "corona": True, "flares": True, "reticle": True, "orbit_alpha": 0.42,
        "belt_density": 0.55, "ship_lod": "full", "msaa": 2, "vsync": True,
        "bloom": False, "shadows": False, "particles": False,
        "drones_fx": True, "surface_detail": True, "map_grid": True,
        "star_twinkle": False, "atmosphere": True,
    },
    "high": {
        "belt": True, "trails": True, "sky": True, "labels": True,
        "corona": True, "flares": True, "reticle": True, "orbit_alpha": 0.55,
        "belt_density": 0.85, "ship_lod": "full", "msaa": 4, "vsync": True,
        "bloom": True, "shadows": False, "particles": True,
        "drones_fx": True, "surface_detail": True, "map_grid": True,
        "star_twinkle": True, "atmosphere": True,
    },
    "ultra": {
        "belt": True, "trails": True, "sky": True, "labels": True,
        "corona": True, "flares": True, "reticle": True, "orbit_alpha": 0.70,
        "belt_density": 1.0, "ship_lod": "full", "msaa": 8, "vsync": True,
        "bloom": True, "shadows": True, "particles": True,
        "drones_fx": True, "surface_detail": True, "map_grid": True,
        "star_twinkle": True, "atmosphere": True,
    },
}
QUALITY_ORDER = ("low", "medium", "high", "ultra")

# Display resolution presets (settings menu). windowed sizes; fullscreen uses
# the desktop mode when the host supports it.
RESOLUTION_ORDER = ("1280x720", "1440x900", "1600x900", "1920x1080", "2560x1440")
DEFAULT_RESOLUTION = "1440x900"
FOV_ORDER = (50, 55, 60, 70)
DEFAULT_FOV = 55
UI_SCALE_ORDER = (0.85, 1.0, 1.15, 1.30)
DEFAULT_UI_SCALE = 1.0
MASTER_VOLUME_STEPS = (0.0, 0.25, 0.5, 0.75, 1.0)
DEFAULT_MASTER_VOLUME = 0.75


# --- camera / view modes -------------------------------------------------------
# network = classic heliocentric 3-D; map = top-down system chart; surface = land
# on the selected body and watch the harvest drones work the veins.
VIEW_MODES = ("network", "map", "surface")
DEFAULT_VIEW_MODE = "network"

