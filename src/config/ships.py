"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- ship ------------------------------------------------------------------
# Propellant budget per ship, in m/s. Electric propulsion flavour (see
# SHIP_ISP), so a large budget is defensible. Sized against the measured cost
# of the network: the Derelict Zone is ~11.3 km/s each way, so a round trip is
# ~23 km/s and 26 km/s leaves real margin without making fuel a non-issue.
# Running out strands a freighter at its destination, which is the intended
# failure mode.
SHIP_START_DELTA_V = 26.0e3
SHIP_CARGO_CAPACITY = 240    # tonnes per run
# Docked freighters regenerate propellant at this rate (m/s per sim-day),
# drawn from colony energy. Without it a fleet grounds itself after two runs
# and the supply chain stops.
SHIP_REFUEL_RATE = 160.0
# Raised from 22 when the economy layer landed: at 22 m/s per day a docked
# freighter could only afford the cheapest hop by the time the 30-day idle
# scan re-dispatched it, so fleets were trapped flying inner-belt runs
# forever. At 160 a ship tops up in under a year of layover, which matches
# the natural rhythm of window waits and lets deep fields open up.
SHIP_REFUEL_ENERGY_PER_MS = 0.0006  # colony energy units per m/s restored
# Lowered from 0.004 when life support gave the colony a real energy budget
# (solar +1.5/day): at 0.004 a single full refill cost ~104 energy, roughly a
# season of sunlight, so the cell sat permanently at zero. At 0.0006 a full
# refill costs ~16, a sensible share of production.
SHIP_ISP = 3200.0            # s, electric propulsion flavour


# --- fleet classes (colony operations layer) -------------------------------
# Data-driven ship classes. The default class reproduces the verified baseline
# freighter exactly, so the starting fleet flies identical missions to before.
# Delta-v differences are honest: a class gets more/less propellant budget and
# hold volume, never a physics discount on the conics themselves.
SHIP_CLASSES = {
    "scout":     {"name": "Scout",     "capacity": 120.0, "delta_v": 30.0e3, "price": 2500.0,
                  "refuel_rate": 170.0, "wear_factor": 0.85, "mine_bonus": 1.0},
    "freighter": {"name": "Freighter", "capacity": SHIP_CARGO_CAPACITY, "delta_v": SHIP_START_DELTA_V,
                  "price": 4500.0, "refuel_rate": SHIP_REFUEL_RATE, "wear_factor": 1.0, "mine_bonus": 1.0},
    "refinery":  {"name": "Refinery",  "capacity": 260.0, "delta_v": 24.0e3, "price": 7500.0,
                  "refuel_rate": 160.0, "wear_factor": 0.70, "mine_bonus": 1.3},
    "hauler":    {"name": "Hauler",    "capacity": 520.0, "delta_v": 21.0e3, "price": 9000.0,
                  "refuel_rate": 200.0, "wear_factor": 1.10, "mine_bonus": 1.0},
    # Logistics specialist: tops up barns fast, modest hold — the hop network's blood.
    "tanker":    {"name": "Tanker",    "capacity": 80.0, "delta_v": 28.0e3, "price": 6200.0,
                  "refuel_rate": 320.0, "wear_factor": 0.90, "mine_bonus": 0.6,
                  "depot_fill_bonus": 1.75},
    # Window specialist: tiny hold, honest long tank — the far-field courier.
    "clipper":   {"name": "Clipper",   "capacity": 90.0, "delta_v": 32.0e3, "price": 7800.0,
                  "refuel_rate": 180.0, "wear_factor": 0.80, "mine_bonus": 0.85},
    # Far-Charter workhorse (v1.6): the long tank that makes Night Well and
    # Boreas routine. Pays for the reach with a slow refill and a lean hold.
    "courser":   {"name": "Courser",   "capacity": 180.0, "delta_v": 36.0e3, "price": 11500.0,
                  "refuel_rate": 150.0, "wear_factor": 0.95, "mine_bonus": 0.90},
    # Bulk argosy (v1.6): a warehouse with an engine. Moves whole seasons of
    # seedstock or silicates in one hold; crawls, drinks, and wears like one.
    "argosy":    {"name": "Argosy",    "capacity": 720.0, "delta_v": 19.0e3, "price": 12500.0,
                  "refuel_rate": 210.0, "wear_factor": 1.30, "mine_bonus": 0.85},
}
DEFAULT_SHIP_CLASS = "freighter"
FLEET_NAME_POOL = ("Kestrel", "Petrel", "Harrier", "Osprey", "Falcon", "Condor",
                   "Raven", "Heron", "Skua", "Gannet", "Tern", "Egret",
                   "Albatross", "Ibis", "Plover", "Snipe", "Curlew", "Stilt")


# --- credits (earned by selling ore on the Earth market) --------------------
START_CREDITS = 600.0


# --- hull wear & maintenance ------------------------------------------------
HULL_MAX_PCT = 100.0
HULL_MIN_PCT = 5.0             # ships never become unrecoverable wrecks
HULL_CRITICAL_PCT = 20.0       # dispatch refused below this (safety interlock)
HULL_WEAR_PCT_PER_MS = 0.0025  # a ~14 km/s round trip costs ~35% hull
HULL_REPAIR_RATE_PCT_PER_DAY = 4.0
HULL_REPAIR_COST_PER_PCT = 12.0  # credits per percentage point restored

