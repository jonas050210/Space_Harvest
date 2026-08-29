"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- refuel depots -----------------------------------------------------------
# Player-built stations at trade bodies. A depot makes its own propellant from
# local ice (ISRU flavour), so ships can top up far from home and fly deep
# runs that a round trip from the colony could never afford. Dispatch counts
# depot stock as the ride home; the ship refuels while it waits for the
# return window.
DEPOT_BUILD_COST = 3500.0          # credits
DEPOT_UPGRADE_COST = 2600.0        # multiplied by 1.6^(level - 1)
DEPOT_CAPACITY_PER_LEVEL = 22000.0  # m/s of stored delta-v per level
DEPOT_GENERATION_PER_LEVEL = 7.0    # m/s per day produced per level
DEPOT_START_FUEL = 9000.0           # m/s in the tank when it comes online
DEPOT_UPGRADE_COST_GROWTH = 1.6


# --- multi-revolution planning -------------------------------------------------
# The window solver can consider transfers with extra full revolutions (slow
# routes). Izzo multi-rev branches only replace the single-rev plan when they
# save at least MIN_SAVING of its cost, so the extra flight time must buy
# real propellant. In this near-coplanar network single-rev Hohmann-class
# windows dominate (as orbital mechanics predicts), so the gate rarely opens;
# strongly perturbed or inclined future targets are where it pays off. Set
# the saving to a negative value to force multi-rev plans (used by tests).
PLANNING_MAX_REVS = 1
PLANNING_MULTI_REV_MIN_SAVING = 0.15


# --- window search ---------------------------------------------------------
WINDOW_GRID_DEPART = 72
WINDOW_GRID_TOF = 30
# Solving a window runs a Lambert grid (~230k Lambert solves for a full fleet
# scan), so round-trip plans are cached this long in sim days. One Earth year
# is shorter than any round trip in the network, so a cached plan is always
# used while a ship is still flying the run it was priced for.
ROUND_TRIP_CACHE_DAYS = 365.0
# How often the idle-fleet dispatch scan may re-price the network.
REDISPATCH_SCAN_DAYS = 30.0

