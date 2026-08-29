"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


try:
    from .progression import FIRSTS
    # FIRSTS is defined in progression.py; import for ACHIEVEMENTS
    # If circular, fallback to empty tuple and resolve later in __init__
except Exception:
    FIRSTS = ()


# --- campaign difficulty -------------------------------------------------------
# Applied only in the game layer (credits, market absorption, wear, contracts).
# The orbital core never sees difficulty names -- only the resulting numbers.
DIFFICULTY_ORDER = ("director", "tight", "ironman")
DIFFICULTY_MODES = {
    "director": {
        "label": "Director",
        "blurb": "Default balance. Learn the windows, build the industry.",
        "start_credits_mult": 1.0,
        "market_absorption_mult": 1.0,
        "hull_wear_mult": 1.0,
        "contract_reward_mult": 1.0,
        "refuel_rate_mult": 1.0,
        "life_solar_mult": 1.0,
        "ironman": False,
        "permadeath_hull": False,
    },
    "tight": {
        "label": "Tight Margins",
        "blurb": "Lean treasury, harsher floods, slower refuel. No mercy pricing.",
        "start_credits_mult": 0.70,
        "market_absorption_mult": 0.70,
        "hull_wear_mult": 1.15,
        "contract_reward_mult": 0.95,
        "refuel_rate_mult": 0.80,
        "life_solar_mult": 0.90,
        "ironman": False,
        "permadeath_hull": False,
    },
    "ironman": {
        "label": "Ironman",
        "blurb": "One save. Critical hulls can wreck. No F9. The belt remembers.",
        "start_credits_mult": 0.85,
        "market_absorption_mult": 0.85,
        "hull_wear_mult": 1.25,
        "contract_reward_mult": 1.05,
        "refuel_rate_mult": 0.85,
        "life_solar_mult": 0.85,
        "ironman": True,
        "permadeath_hull": True,
    },
}
DEFAULT_DIFFICULTY = "director"


# --- victory / campaign goals --------------------------------------------------
# Player picks one at NEW HARVEST. Endless never ends; charter is the Steam clear.
VICTORY_ORDER = ("endless", "charter", "legacy", "worldseed")
VICTORY_MODES = {
    "endless": {
        "label": "Endless Director",
        "blurb": "No win screen. Seasonal Firsts forever.",
        "credits": 0.0,
        "tonnage": 0.0,
        "aurellium": False,
        "firsts_needed": 0,
    },
    "charter": {
        "label": "Charter Complete",
        "blurb": "100k cr, 10,000 t delivered, first aurellium shipment.",
        "credits": 100_000.0,
        "tonnage": 10_000.0,
        "aurellium": True,
        "firsts_needed": 0,
    },
    "legacy": {
        "label": "Colony Legacy",
        "blurb": "Hit 15 Firsts and keep the pantry alive -- a lasting charter.",
        "credits": 50_000.0,
        "tonnage": 5_000.0,
        "aurellium": False,
        "firsts_needed": 15,
    },
    "worldseed": {
        "label": "Worldseed",
        "blurb": "Garden 80, a seedstock shipment, 8,000 t hauled.",
        "credits": 40_000.0,
        "tonnage": 8_000.0,
        "aurellium": False,
        "firsts_needed": 0,
        "garden": 80.0,
        "seedstock": True,
    },
}
DEFAULT_VICTORY = "endless"

# Steam achievement ids mirror Firsts keys plus a few secrets. The runtime
# writes steam/achievements_progress.json; a Steamworks wrapper can poll it.
ACHIEVEMENTS = tuple(key for key, _label, _c, _r in FIRSTS) + (
    "secret_stranded_rescue",
    "secret_zero_incident_streak",
    "secret_charter_clear",
    "secret_ironman_year",
    "secret_worldseed",
)

