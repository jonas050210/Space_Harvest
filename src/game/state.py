"""Colony economy state used by the orbital supply-chain shell.

The full upstream colony builder is gone; this module keeps the small surface
the orbital game needs: initial resource stocks, storage helpers, and the
logistics book the freighters write into.
"""

from __future__ import annotations

from . import config, settings


def initial_state():
    return {
        "resources": {
            "ice": 200, "iron": 150, "gold": 10, "silver": 5, "platinum": 0,
            "energy": 20, "water": 0, "components": 0, "electronics": 0,
            "thorite": 0, "aurellium": 0,
        },
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
    }


def get_diff_factor(state):
    name = state.get("difficulty", config.DEFAULT_DIFFICULTY)
    return config.DIFFICULTY.get(name, 1.0)


def resource_ok(state, cost_dict, factor=1.0):
    mult = get_diff_factor(state) * factor
    for key, value in cost_dict.items():
        if state["resources"].get(key, 0) < value * mult:
            return False
    return True


def deduct_resources(state, cost_dict, factor=1.0):
    mult = get_diff_factor(state) * factor
    for key, value in cost_dict.items():
        state["resources"][key] = state["resources"].get(key, 0) - value * mult


def add_resources(state, res_dict):
    for key, value in res_dict.items():
        state["resources"][key] = state["resources"].get(key, 0) + value
