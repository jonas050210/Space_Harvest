"""Colony economy state used by the orbital supply-chain shell.

The full upstream colony builder is gone; this module keeps the small surface
the orbital game needs: initial resource stocks, storage helpers, and the
logistics book the freighters write into.
"""

from __future__ import annotations

from . import config, settings


def _base_resources() -> dict[str, float]:
    # Core starter stocks - keep gameplay values, but ensure every ore from
    # MINING_ORES exists (future-proof when new ores are added).
    base: dict[str, float] = {
        "ice": 200,
        "iron": 150,
        "gold": 10,
        "silver": 5,
        "platinum": 0,
        "energy": 20,
        "water": 0,
        "components": 0,
        "electronics": 0,
        "thorite": 0,
        "aurellium": 0,
        "silicates": 0,
        "obsidian": 0,
        "helium3": 0,
        "cobalt": 0,
        "magnetite": 0,
        "xenonite": 0,
        "seedstock": 0,
        "memory_glass": 0,
    }
    try:
        from src.config import MINING_ORES
        for ore in MINING_ORES:
            base.setdefault(ore, 0)
    except Exception:
        pass
    return base


def initial_state() -> dict:
    return {
        "resources": _base_resources(),
        "garden_score": 0.0,
        "population": 3,
        "max_pop": 8,
        "max_energy": 30,
        "modules": ["drone_bay", "solar_panel"],
        "station_level": 1,
        "difficulty": settings.load().get("difficulty", config.DEFAULT_DIFFICULTY),
        "language": "en",
        "score": 0,
        "research_points": 0.0,
        "research": {"unlocked": []},
        "logistics": {"lifetime_delivered": {}, "production": {}},
        "run_stats": {"resources_delivered": 0},
        "warehouse_bonus_t": 0.0,
    }


def add_resources(state: dict, res_dict: dict[str, float]) -> None:
    for key, value in res_dict.items():
        state["resources"][key] = state["resources"].get(key, 0) + value
