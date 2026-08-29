"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- station modules (body-side industry) ------------------------------------
# Built at a selected field with keys; effects are ops multipliers / storage.
STATION_MODULE_CATALOG = {
    "observatory": {
        "name": "Field Observatory", "cost": 2800.0,
        "research_per_day": 0.15, "max_per_body": 1,
        "blurb": "Passive research while the barn watches the sky.",
    },
    "warehouse": {
        "name": "Orbital Warehouse", "cost": 3600.0,
        "storage_bonus": 200.0, "max_per_body": 2,
        "blurb": "Colony storage capacity via bonded holds.",
    },
    "drill_yard": {
        "name": "Drill Yard", "cost": 4100.0,
        "mine_bonus": 0.15, "max_per_body": 1,
        "blurb": "Surface rigs boost every freighter capture here.",
    },
    "shield_mast": {
        "name": "Shield Mast", "cost": 3300.0,
        "weather_resist": 0.5, "max_per_body": 1,
        "blurb": "Halves flare/debris wear for ships waiting here.",
    },
    "greenhouse": {
        "name": "Greenhouse Dome", "cost": 3900.0,
        "research_per_day": 0.08, "garden_ice_per_day": 0.45, "max_per_body": 2,
        "blurb": "Drinks ice, grows garden score, trickles research.",
    },
    "foundry": {
        "name": "Field Foundry", "cost": 4400.0,
        "refinery_bonus": 0.5, "max_per_body": 1,
        "blurb": "Speeds the mill while ships wait here.",
    },
}


# --- surface survey / ISRU spikes ---------------------------------------------
# Landing on a field is not only spectacle: Survey reveals richer veins for a
# while; planting an ISRU spike permanently boosts that body's depot generation
# if a barn exists (or the next barn built there).
SURFACE_SURVEY_COST_CR = 150.0
SURFACE_SURVEY_BONUS = 0.20          # +20% extraction on that body
SURFACE_SURVEY_DAYS = 400.0          # bonus duration
SURFACE_ISRU_COST_CR = 1200.0
SURFACE_ISRU_DEPOT_GEN_BONUS = 2.5   # extra m/s per day on that body's depot
SURFACE_ISRU_MAX_PER_BODY = 2


# --- garden / worldseed -------------------------------------------------------
# Greenhouse domes drink colony ice and raise a garden score. Techs may scale
# it via tech_mults["garden"]. This is ops+game layer only — not physics.
GARDEN_SCORE_PER_ICE = 1.0
GARDEN_START = 0.0


# --- rival charter (light antagonist) ----------------------------------------
# A competing outfit quietly mines the same veins. They do not fly visible
# ships; they accelerate depletion and occasionally dump ore on Earth.
RIVAL_ENABLED_DEFAULT = True
RIVAL_MINE_T_PER_DAY = 0.35          # tonnes drawn from a random trade body / day
RIVAL_DUMP_PERIOD_DAYS = 180.0
RIVAL_DUMP_TONNES = (20.0, 80.0)
RIVAL_NAME = "Helios Syndicate"

