"""Window / UI and product identity + default settings."""

from __future__ import annotations

GAME_NAME = "Space Harvest"
GAME_TAGLINE = "wait for the window  --  harvest the belt  --  keep the colony alive"
WINDOW_TITLE = "Space Harvest"
WINDOW_SIZE = (1440, 900)
STEAM_APP_ID = 0
GAME_VERSION = "1.6.1"
EXECUTABLE_NAME = "SpaceHarvest"

# Default settings blob persisted in saves/_settings.json
# Defined here to avoid circular imports - values are literals matching original
DEFAULT_SETTINGS = {
    "quality": "medium",
    "muted": False,
    "glide": True,
    "resolution": "1440x900",
    "fullscreen": False,
    "vsync": True,
    "fov": 55,
    "ui_scale": 1.0,
    "master_volume": 0.75,
    "difficulty": "director",
    "victory": "endless",
    "show_dossier": True,
    "confirm_dispatch": True,
    "prefer_hops": True,
    "view_mode": "network",
    "show_map_grid": True,
    "show_surface_hud": True,
    "drone_fx": True,
    "ui_contrast": True,
    "rival_enabled": True,
    "show_route_overlay": True,
}

SAVE_SLOTS = ("quick", "slot1", "slot2", "slot3")
