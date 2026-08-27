"""Global constants for the orbital supply-chain prototype.

Unit conventions
----------------
The orbital layer works in its own scaled system chosen so the numbers stay
readable:

* length unit  : ``AU``  (1 AU = 1.0)
* ``MU_SUN``   : ``4 * pi^2``, so a circular orbit at a = 1 AU has a period of
  exactly ``2 * pi`` simulation seconds.

With ``mu = 4 pi^2`` the natural velocity unit is **AU per year**, not AU per
simulation second: ``sqrt(mu / 1 AU) = 2 pi`` AU/yr is exactly Earth's mean
orbital speed. Convert to km/s by multiplying with ``AU_PER_YEAR_TO_KM_S``.
Getting this wrong is easy and costly, so the conversion is centralised here
and covered by a test.

Render scaling
--------------
The Ursina scene is far smaller than the solar system, so body positions are
compressed by ``SCENE_UNITS_PER_AU`` for display only. The physics never sees
the render scale.
"""

from __future__ import annotations

import math

# --- simulation units ------------------------------------------------------
MU_SUN = 4.0 * math.pi ** 2          # so a = 1 AU has T = 2*pi sim-seconds
SIM_SECONDS_PER_YEAR = 2.0 * math.pi  # one Earth year in simulation seconds
SIM_SECONDS_PER_DAY = SIM_SECONDS_PER_YEAR / 365.25

AU_KM = 1.495978707e8
SECONDS_PER_YEAR = 365.25 * 86400.0
# Multiply a velocity expressed in AU/year by this to get km/s.
AU_PER_YEAR_TO_KM_S = AU_KM / SECONDS_PER_YEAR  # ~4.7405 km/s

# --- render scaling --------------------------------------------------------
SCENE_UNITS_PER_AU = 8.0   # Aurelia at 2.8 AU sits ~22 scene units from the sun

# --- pacing ----------------------------------------------------------------
DEFAULT_TIME_WARP_DAYS_PER_SECOND = 12.0  # sim days advanced per real second
TIME_WARP_STEPS = (1.0, 6.0, 24.0, 90.0)  # cycled with [ and ]

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
}
DEFAULT_SHIP_CLASS = "freighter"
FLEET_NAME_POOL = ("Kestrel", "Petrel", "Harrier", "Osprey", "Falcon", "Condor",
                   "Raven", "Heron", "Skua", "Gannet", "Tern", "Egret")

# --- credits (earned by selling ore on the Earth market) --------------------
START_CREDITS = 600.0

# --- hull wear & maintenance ------------------------------------------------
HULL_MAX_PCT = 100.0
HULL_MIN_PCT = 5.0             # ships never become unrecoverable wrecks
HULL_CRITICAL_PCT = 20.0       # dispatch refused below this (safety interlock)
HULL_WEAR_PCT_PER_MS = 0.0025  # a ~14 km/s round trip costs ~35% hull
HULL_REPAIR_RATE_PCT_PER_DAY = 4.0
HULL_REPAIR_COST_PER_PCT = 12.0  # credits per percentage point restored

# --- mining: ore fingerprints, depletion, extraction modes -------------------
MINING_SEED = 20260826         # combined with the body key, deterministic
MINING_ORES = ("ice", "iron", "silver", "gold", "platinum", "components", "electronics")
# Vein size per ore in tonnes: after extracting one vein-size the yield is at
# 1/e, forcing expansion to fresh rocks while slow recovery keeps the game
# from dead-ending.
MINING_VEIN_SIZE_T = {"ice": 1200.0, "iron": 1600.0, "silver": 700.0,
                      "gold": 450.0, "platinum": 300.0, "components": 500.0, "electronics": 250.0}
MINING_DRILL_YIELD_BONUS = 1.6   # core drilling multiplier per run
MINING_DRILL_WEAR_PCT = 6.0      # hull cost of drilling on every drilled run
MINING_LOW_HULL_YIELD_PCT = 40.0  # below this hull %, yield scales with hull
MINING_RECOVERY_TAU_DAYS = 2400.0  # e-folding time for depleted veins to recover
# Volatiles replenish much faster than metals: ices migrate and re-condense,
# so a mined-out ice field comes back within a few years instead of decades.
MINING_RECOVERY_TAU_BY_ORE = {"ice": 900.0}
INCIDENT_CHANCE_SCRAPE = 0.02      # per capture
INCIDENT_CHANCE_DRILL = 0.09       # per capture while core drilling
INCIDENT_LOW_HULL_FACTOR = 1.2     # extra chance = factor * max(0, 40-hull)/100
INCIDENT_CARGO_LOSS = 0.35         # fraction of the delivery lost to an incident

# --- Earth market: dynamic pricing ------------------------------------------
MARKET_BASE_PRICES = {  # credits per tonne
    "ice": 8.0, "iron": 12.0, "silver": 40.0, "gold": 90.0,
    "platinum": 220.0, "components": 65.0, "electronics": 160.0,
}
# Tonnes the Earth market absorbs before the price visibly sags; rare ores
# flood much faster, so dumping a hauler load of platinum crashes its price.
MARKET_ABSORPTION_T = {"ice": 400.0, "iron": 320.0, "silver": 140.0, "gold": 60.0,
                       "platinum": 30.0, "components": 80.0, "electronics": 40.0}
MARKET_FLOOD_HALF_LIFE_DAYS = 30.0
MARKET_SEASONAL_AMPLITUDE = 0.22
MARKET_SEASONAL_PERIOD_DAYS = {"ice": 240.0, "iron": 300.0, "silver": 360.0,
                               "gold": 420.0, "platinum": 480.0, "components": 390.0, "electronics": 450.0}
MARKET_NOISE_SIGMA = 0.05           # random-walk strength, per sqrt(day)
MARKET_NOISE_MEAN_REVERSION = 0.02  # per day toward demand 1.0
MARKET_PRICE_FLOOR_FRACTION = 0.15  # price never drops below this share of base
MARKET_HISTORY_SAMPLE_DAYS = 2.0
MARKET_HISTORY_POINTS = 240

# --- crew: roster, morale, fatigue ------------------------------------------
# Every ship carries a small crew drawn from the colony pool. Tired crews
# cause mining incidents; unpaid or deprived crews work slower; crews that
# rest too long get bored. Effects are multiplicative factors on systems that
# already exist (incident rolls, extraction planning), never new physics.
# Rates are budgeted against a typical ~150 away-day round trip: fatigue
# should come home around 80, and a season docked plus payday should restore
# morale fully, so crews are "tired but eager", not destroyed, by one run.
CREW_MORALE_START = 80.0
CREW_MORALE_MAX = 100.0
CREW_FATIGUE_PER_DAY_FLYING = 0.45   # OUTBOUND / INBOUND legs
# Layovers are long (return windows can open months after arrival) but they
# are NOT hard work: station-keeping on a captured body is light duty, so
# fatigue accrues slowly and morale only suffers mild cabin fever.
CREW_FATIGUE_PER_DAY_LAYOVER = 0.15  # WAITING: light station-keeping duty
CREW_FATIGUE_PER_DAY_PENDING = 0.05  # pre-launch prep while still docked home
CREW_MORALE_CABIN_FEVER_PER_DAY = 0.05  # WAITING: cooped up far from home
CREW_FATIGUE_RECOVERY_PER_DAY = 1.8  # docked at the colony
CREW_FATIGUE_EXHAUSTED = 90.0        # dispatch refused above this
CREW_MORALE_CAPTURE_BONUS = 3.0      # a clean capture pays in pride
CREW_MORALE_PAYDAY_BONUS = 2.0       # granted when ore is sold
CREW_MORALE_REST_PER_DAY = 0.8       # parked, fed, paid
CREW_MORALE_OVERWORK_DRAIN_PER_DAY = 0.3  # per member while own fatigue > 70
CREW_MORALE_BOREDOM_DRAIN_PER_DAY = 0.3   # parked longer than this...
CREW_IDLE_BOREDOM_DAYS = 45.0             # ...while fully rested
CREW_MORALE_BOREDOM_FLOOR = 25.0  # boredom alone never breaks a crew; shortages can
CREW_MORALE_OVERWORK_FLOOR = 45.0  # overwork sours morale but never breaks it
CREW_MORALE_LOW_YIELD = 35.0         # below this morale, mining yield suffers
# Specialisations: signing bonuses in credits, and what each role does.
# Pilots shave burns (skill, not physics: the ops layer refunds the saved
# propellant after the core bills the real manoeuvre), engineers speed hull
# repairs docked, botanists cut the water cost of hydroponics colony-wide.
CREW_HIRE_COST = {"pilot": 900.0, "miner": 600.0, "engineer": 1100.0, "botanist": 800.0}
CREW_MAX_ROSTER = 6
CREW_PILOT_BURN_DISCOUNT = 0.03     # per pilot aboard, capped at 0.05
CREW_PILOT_DISCOUNT_CAP = 0.05
CREW_ENGINEER_REPAIR_BONUS = 0.5    # +50% repair rate with an engineer aboard
CREW_BOTANIST_WATER_SAVING = 0.08   # per botanist, capped at 0.32
CREW_BOTANIST_SAVING_CAP = 0.32
CREW_FIRE_MORALE_HIT = 6.0          # survivors resent a dismissal

# --- gravitational perturbations ----------------------------------------------
# A passing body occasionally shifts a belt body's orbit slightly. The
# operations layer owns copies of the body table, so the verified core and
# its module-level constants stay untouched; caches are invalidated and the
# fleet re-plans from the new geometry.
PERTURB_MIN_INTERVAL_DAYS = 500.0
PERTURB_MAX_INTERVAL_DAYS = 950.0
PERTURB_DA_FRACTION = (0.005, 0.02)  # semi-major-axis shift as a fraction
PERTURB_DE_MAX = 0.012
CREW_NAMES_FIRST = ("Yuki", "Mateo", "Aria", "Dmitri", "Zaneh", "Okafor", "Lena",
                    "Tariq", "Ines", "Kofi", "Mira", "Anders", "Priya", "Hugo",
                    "Farida", "Jonas", "Nova", "Rafael", "Sanaa", "Emil")
CREW_NAMES_LAST = ("Voss", "Okoye", "Lindqvist", "Marsh", "Petrov", "Duarte",
                   "Haile", "Kowalski", "Nakamura", "Silva", "Adeyemi", "Ferro")

# --- space weather: solar flares and debris seasons --------------------------
# Global, deterministic, ticked by the operations step. Only ships in flight
# are exposed; docked ships sit inside the colony's shielding.
FLARE_QUIET_DAYS_RANGE = (120.0, 420.0)  # quiet-time draw before the next cycle
FLARE_WARNING_DAYS = 6.0                 # HUD-visible warning before it hits
FLARE_DURATION_DAYS_RANGE = (2.0, 5.0)
FLARE_WEAR_PCT_PER_DAY = 1.2             # extra hull wear for ships in flight
FLARE_MORALE_DRAIN_PER_DAY = 0.8         # crews hate riding out a storm
DEBRIS_SEASON_PERIOD_DAYS = 300.0        # roughly periodic debris seasons
DEBRIS_SEASON_DURATION_DAYS = 40.0
DEBRIS_WEAR_PCT_PER_DAY = 0.35           # micrometeorite sandblasting in flight

# --- Earth faction contracts --------------------------------------------------
CONTRACT_FACTIONS = ("Terran Metals Guild", "Luna Water Authority", "Ceres Prospecting Co.")
CONTRACT_OFFER_PERIOD_DAYS = 70.0
CONTRACT_MAX_ACTIVE = 2
CONTRACT_TONNES_RANGE = (60.0, 260.0)
# Deadlines must match the network's rhythm: a round trip takes 500-700 days
# with windows and layovers, so anything shorter is a toll on standing, not a
# game.
CONTRACT_DEADLINE_DAYS = (420.0, 720.0)
CONTRACT_REWARD_MULTIPLIER_RANGE = (1.15, 1.45)  # x market price at offering
CONTRACT_REP_ON_COMPLETE = 12.0
CONTRACT_REP_ON_FAIL = 18.0
REPUTATION_PRICE_BONUS = 0.06  # max sell-price swing at +/-100 average standing

# --- colony life support (ticked by the game layer) ---------------------------
# Crew consume oxygen, food and water. Electrolysis and hydroponics regenerate
# them from water and energy; an ice refinery melts stored ice into water. The
# loop creates the core tension: ice sold to Earth is ice the colonists do not
# eat. All units are abstract life-support units per crew member per day.
# Rates are budgeted so one mixed inner-belt hold (~130 t of ice) feeds the
# starting crew for about 250 days: incidental deliveries mostly cover the
# colony, deliberate ice runs cover growth, and selling everything starves it.
LIFE_OXYGEN_PER_CREW_DAY = 0.008
LIFE_FOOD_PER_CREW_DAY = 0.0064
LIFE_WATER_PER_CREW_DAY = 0.0048
# Closed-loop recycling: most of the water the crew and the processors use is
# reclaimed (ISS-style), so only the net loss must be replaced from the ice
# refinery. This is what makes a growing fleet life-supportable at all given
# that an inner-belt round trip takes ~600 days of windows and layovers.
LIFE_WATER_RECYCLE_FRACTION = 0.6
LIFE_ELECTROLYSIS_WATER_PER_O2 = 1.2
LIFE_ELECTROLYSIS_ENERGY_PER_O2 = 0.4
LIFE_HYDROPONICS_WATER_PER_FOOD = 1.1
LIFE_HYDROPONICS_ENERGY_PER_FOOD = 0.5
LIFE_ICE_TO_WATER_YIELD = 0.8
LIFE_ICE_MELT_RATE_PER_DAY = 8.0
# Life support bids against the market for ice: when the effective water
# buffer (tank + melt-able ice) covers fewer than HORIZON days of crew life,
# the dispatcher values ice up to PREMIUM_MAX credits per tonne above the
# market price. This is what keeps the auto-economy from selling the
# colonists' ice to Earth and then starving.
LIFE_ICE_HORIZON_DAYS = 400.0
LIFE_ICE_PREMIUM_MAX = 60.0
LIFE_ICE_RESERVE_T = 80.0        # S never sells the colonists' ice below this
LIFE_START_OXYGEN = 40.0
LIFE_START_FOOD = 35.0
LIFE_START_WATER = 30.0
LIFE_LOW_STOCK_FRACTION = 0.25   # HUD alert + audio warning below this
LIFE_SHORTAGE_MORALE_DRAIN_PER_DAY = 3.0
# The colony's solar array: without a positive energy source the refuel and
# life-support energy bills would drain the cell to zero and stall everything.
LIFE_SOLAR_ENERGY_PER_DAY = 1.5


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

# --- window / UI ------------------------------------------------------------
WINDOW_TITLE = "Asteroid Colony Proto - Orbital Supply Chains"
WINDOW_SIZE = (1440, 900)
