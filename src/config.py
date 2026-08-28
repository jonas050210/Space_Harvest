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
MINING_ORES = ("ice", "iron", "silver", "gold", "platinum", "components", "electronics",
               "thorite", "aurellium", "silicates", "obsidian", "helium3")
# Vein size per ore in tonnes: after extracting one vein-size the yield is at
# 1/e, forcing expansion to fresh rocks while slow recovery keeps the game
# from dead-ending.
MINING_VEIN_SIZE_T = {"ice": 1200.0, "iron": 1600.0, "silver": 700.0,
                      "gold": 450.0, "platinum": 300.0, "components": 500.0, "electronics": 250.0,
                      "thorite": 380.0, "aurellium": 140.0,
                      "silicates": 900.0, "obsidian": 220.0, "helium3": 90.0}
# Campaign-only ore spawns, appended to a body's module-declared resources.
# The deep belt and the derelict hull carry radioactive thorite in their slag;
# aurellium exists ONLY in the comet -- the jackpot that makes the chase pay.
MINING_EXTRA_SPAWNS = {
    "deep_belt": ("thorite", "silicates"),
    "derelict_zone": ("thorite",),
    "comet_vigil": ("thorite", "aurellium", "helium3"),
    "trojan_field": ("ice", "silicates", "silver"),
    "cinder_moon": ("platinum", "obsidian", "gold"),
    "outer_reach": ("helium3", "thorite", "platinum"),
}
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
    "thorite": 70.0, "aurellium": 480.0,
    "silicates": 18.0, "obsidian": 310.0, "helium3": 520.0,
}
# Tonnes the Earth market absorbs before the price visibly sags; rare ores
# flood much faster, so dumping a hauler load of platinum crashes its price.
MARKET_ABSORPTION_T = {"ice": 400.0, "iron": 320.0, "silver": 140.0, "gold": 60.0,
                       "platinum": 30.0, "components": 80.0, "electronics": 40.0,
                       "thorite": 45.0, "aurellium": 12.0,
                       "silicates": 200.0, "obsidian": 22.0, "helium3": 10.0}
MARKET_FLOOD_HALF_LIFE_DAYS = 30.0
MARKET_SEASONAL_AMPLITUDE = 0.22
MARKET_SEASONAL_PERIOD_DAYS = {"ice": 240.0, "iron": 300.0, "silver": 360.0,
                               "gold": 420.0, "platinum": 480.0, "components": 390.0, "electronics": 450.0,
                               "thorite": 330.0, "aurellium": 540.0,
                               "silicates": 280.0, "obsidian": 400.0, "helium3": 600.0}
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


# --- upgrade parts (Earth parts market) ---------------------------------------
# Buy with T (tank) / Y (drill) / U (quarters) for a docked ship, P for a
# depot drone bay. Prices ride the same seasonal/noise economy as ore: buy
# tanks when the parts market is cheap. Escalating counts keep it a decision.
PARTS_CATALOG = {
    "tank": {"name": "Drop Tanks", "base_price": 1800.0, "delta_v": 3500.0, "max_per_ship": 2},
    "drill": {"name": "Deep Drill", "base_price": 2400.0, "mine_bonus": 0.25, "max_per_ship": 2},
    "quarters": {"name": "Crew Quarters", "base_price": 1500.0, "rest_bonus": 0.5, "max_per_ship": 1},
    "drones": {"name": "Depot Drone Bay", "base_price": 3200.0, "mine_per_day": 5.0, "max_per_depot": 2},
    # The aurellium super-part: comet loot becomes campaign power. Op-layer
    # trajectory-planning skill (like pilots), never a physics change.
    "navsuite": {"name": "Navigation Suite", "base_price": 5200.0, "refund": 0.05,
                 "max_per_ship": 1, "aurellium_t": 6},
}
PARTS_PRICE_ESCALATION = 1.25
PARTS_SEASON_DAYS = {"tank": 300.0, "drill": 340.0, "quarters": 260.0, "drones": 400.0,
                     "navsuite": 600.0}

# --- the comet ----------------------------------------------------------------
# "Vigil" is a long-period comet: perihelion inside the inner belt, aphelion
# deep beyond Aurelia. Its windows are rare and its arrival moves FAST, so
# captures there are brutally expensive -- depot-assisted runs shine. The ore
# is the jackpot: primordial ices and platinum-group metal from the slag crust.
COMET_KEY = "comet_vigil"
COMET_ELEMENTS = {"a": 4.45, "e": 0.80, "i_deg": 12.0, "raan_deg": 210.0,
                  "argp_deg": 15.0, "nu_deg": 170.0}
COMET_VEIN_BONUS = 1.0     # multiplier on its per-ore vein sizes
COMET_TAIL_AU = 0.55       # tail sprite length at perihelion (scene-side)

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

# --- refinery stations ----------------------------------------------------------
# A refinery smelts raw ore in a docked (waiting) ship's hold: components from
# iron+silver, electronics from gold. Refined stock sells far above raw ore,
# which is the whole economic reason to build one. The station crafts even
# while no ship is there only in tiny amounts -- it is a service, not a factory.
REFINERY_BUILD_COST = 4200.0
REFINERY_BATCHES_PER_DAY = 3.0
# Smelting passes run against a run's payload the moment the ship docks --
# this is the refinery's core service: the run arrives REFINED.
REFINERY_ARRIVAL_BATCHES = 14
REFINERY_RECIPES = (
    {"output": "components", "amount": 2.0, "input": {"iron": 3.0, "silver": 1.0}},
    {"output": "electronics", "amount": 2.0, "input": {"gold": 3.0}},
)

# --- "Firsts": KSP-style one-shot milestones -------------------------------------
# (key, toast label, credit bonus, research bonus). Checked by the game layer
# every few frames against read-only campaign state; each fires exactly once.
FIRSTS = (
    ("first_dispatch", "First sowing -- a freighter leaves the barn", 250.0, 2.0),
    ("first_capture_belt", "First harvest: the inner belt", 200.0, 2.0),
    ("first_capture_metallic", "First harvest: the metallic belt", 350.0, 4.0),
    ("first_capture_deep", "First harvest: the deep belt", 700.0, 8.0),
    ("first_capture_derelict", "First harvest: the Derelict Zone", 900.0, 10.0),
    ("first_capture_aurelia", "First harvest: Aurelia orbit", 800.0, 8.0),
    ("first_capture_comet", "COMET HARVEST -- aurellium fields open", 2500.0, 40.0),
    ("first_depot", "First barn online -- depot refuelling", 500.0, 5.0),
    ("first_refinery", "First mill smelting", 600.0, 6.0),
    ("first_drones", "Field drones operational", 400.0, 4.0),
    ("full_return_1", "First full-hold harvest home", 300.0, 3.0),
    ("full_return_10", "Ten full holds -- a proper outfit", 1200.0, 12.0),
    ("mass_2500", "2,500 t hauled to the colony", 800.0, 8.0),
    ("mass_10000", "10,000 t -- the belt is a farm", 3000.0, 30.0),
    ("fleet_5", "Five ships under charter", 600.0, 6.0),
    ("rich_25k", "Treasury passes 25,000 cr", 0.0, 10.0),
    ("rich_100k", "Treasury passes 100,000 cr", 0.0, 25.0),
    ("thorite_1", "First thorite harvest", 500.0, 6.0),
    ("aurellium_1", "First aurellium sale -- Earth is stunned", 2000.0, 30.0),
    ("first_capture_trojan", "First harvest: Trojan Field (Aurelia L4)", 700.0, 8.0),
    ("first_capture_cinder", "First harvest: Cinder Moon", 900.0, 10.0),
    ("first_capture_outer", "First harvest: Outer Reach -- the far farm", 1500.0, 20.0),
    ("first_multihop", "First multi-stop delivery (refuel hop)", 800.0, 10.0),
    ("helium3_1", "First helium-3 harvest", 1200.0, 15.0),
    ("obsidian_1", "First cinder obsidian shipment", 900.0, 10.0),
    ("first_swarm", "First hundred-drone window harvest", 1000.0, 12.0),
    ("first_surface", "First surface survey of a field", 300.0, 4.0),
    ("first_system_map", "System chart opened -- the whole farm at once", 200.0, 2.0),
)


# --- campaign deep fields (installed by OpsSimulation, not the module BODIES table) ---
# Trojan Field sits near Aurelia's L4; Cinder is a volcanic moon-analogue on a
# tight Aurelia-like orbit; Outer Reach is the multi-hop endgame rock.
CAMPAIGN_BODIES = {
    "trojan_field": {
        "name": "Trojan Field",
        "elements": {"a": 2.80, "e": 0.04, "i_deg": 2.2, "raan_deg": 40.0,
                     "argp_deg": 20.0, "nu_deg": 330.0},  # ~L4 leading Aurelia
        "radius_km": 14.0, "soi_km": 32000.0,
        "palette": (0.78, 0.88, 0.72),
        "resources": ("ice", "silicates", "silver"),
        "description": "Aurelia L4 trojans -- stable ice and silicate fields.",
        "render_scale": 0.7,
    },
    "cinder_moon": {
        "name": "Cinder Moon",
        "elements": {"a": 2.95, "e": 0.08, "i_deg": 5.5, "raan_deg": 55.0,
                     "argp_deg": 100.0, "nu_deg": 40.0},
        "radius_km": 9.0, "soi_km": 22000.0,
        "palette": (0.92, 0.35, 0.22),
        "resources": ("platinum", "obsidian", "gold"),
        "description": "Volcanic rock -- hazard-rich, obsidian and platinum veins.",
        "render_scale": 0.5,
    },
    "outer_reach": {
        "name": "Outer Reach",
        "elements": {"a": 5.10, "e": 0.22, "i_deg": 9.0, "raan_deg": 280.0,
                     "argp_deg": 160.0, "nu_deg": 20.0},
        "radius_km": 22.0, "soi_km": 50000.0,
        "palette": (0.35, 0.55, 0.95),
        "resources": ("helium3", "thorite", "platinum"),
        "description": "Far-system prospect -- multi-hop depot runs required.",
        "render_scale": 0.85,
    },
}

# --- multi-stop delivery planner (KSP-style refuel hops) --------------------
# Planner may insert player depots as intermediate stops so a ship that cannot
# afford a direct round trip still reaches deep fields. Max hops caps the
# search; cost_slack lets a slightly dearer hop route win if it opens sooner.
ROUTE_MAX_HOPS = 2
ROUTE_COST_SLACK = 1.08          # hop route may cost up to 8% more than direct
ROUTE_PREFER_DEPOT_HOPS = True   # default standing policy

# --- science unlocks -------------------------------------------------------------
# Research points (from deliveries, Firsts, observatories) buy one-shot colony
# technologies. Effects are plain multipliers/discounts the game layer applies
# to existing systems -- the sim only ever sees generic numbers.
TECHS = (
    ("standard_contracts", "Standardised Contracts", 40, {"parts_discount": 0.15}),
    ("crew_rotation", "Crew Rotation Programme", 50, {"fatigue": 0.75}),
    ("isru_catalysts", "ISRU Catalysts", 55, {"depot_generation": 1.5}),
    ("plasma_lances", "Plasma Smelting Lances", 70, {"refinery": 1.5}),
)

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
VICTORY_ORDER = ("endless", "charter", "legacy")
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
}
DEFAULT_VICTORY = "endless"

# Steam achievement ids mirror Firsts keys plus a few secrets. The runtime
# writes steam/achievements_progress.json; a Steamworks wrapper can poll it.
ACHIEVEMENTS = tuple(key for key, _label, _c, _r in FIRSTS) + (
    "secret_stranded_rescue",
    "secret_zero_incident_streak",
    "secret_charter_clear",
    "secret_ironman_year",
)

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

# --- harvest drone swarms ------------------------------------------------------
# When a launch window is open, the director can flood a field with drones.
# Drones are presentation + economy: they pull ore into colony storage over a
# short window burst, gated by drone-bay levels across the network. Graphics
# scale with quality presets (drones_fx).
SWARM_BASE_DRONES = 12                 # visual count at 1 bay-level
SWARM_DRONES_PER_BAY = 18              # extra visuals per total drone-bay level
SWARM_MAX_DRONES = 100                 # hard cap (the "crazy 100" moment)
SWARM_DURATION_DAYS = 14.0             # how long a swarm harvests after launch
SWARM_YIELD_T_PER_DRONE_DAY = 0.85     # tonnes into colony storage per drone-day
SWARM_CREDIT_COST_PER_DRONE = 8.0      # ops cost billed at launch
SWARM_ENERGY_COST_PER_DRONE = 0.04
SWARM_MIN_WINDOW_DAYS = 0.0            # may launch only while window is open (GO)
SWARM_COOLDOWN_DAYS = 40.0             # per-body cooldown after a swarm


# Default settings blob persisted in saves/_settings.json
DEFAULT_SETTINGS = {
    "quality": "medium",
    "muted": False,
    "glide": True,
    "resolution": DEFAULT_RESOLUTION,
    "fullscreen": False,
    "vsync": True,
    "fov": DEFAULT_FOV,
    "ui_scale": DEFAULT_UI_SCALE,
    "master_volume": DEFAULT_MASTER_VOLUME,
    "difficulty": DEFAULT_DIFFICULTY,
    "victory": DEFAULT_VICTORY,
    "show_dossier": True,
    "confirm_dispatch": True,
    "prefer_hops": True,
    "view_mode": DEFAULT_VIEW_MODE,
    "show_map_grid": True,
    "show_surface_hud": True,
    "drone_fx": True,
    "ui_contrast": True,
}

# Named save slots exposed in the pause menu (plus "quick" for F5).
SAVE_SLOTS = ("quick", "slot1", "slot2", "slot3")


# --- window / UI ------------------------------------------------------------
# Product name: Space Harvest — orbital farming on real launch windows.
GAME_NAME = "Space Harvest"
GAME_TAGLINE = "wait for the window  --  harvest the belt  --  keep the colony alive"
WINDOW_TITLE = "Space Harvest"
WINDOW_SIZE = (1440, 900)
# Steamworks app id placeholder (replace before store launch). Zero means
# "no Steam"; steam_appid.txt is written beside the executable by the packager.
STEAM_APP_ID = 0
GAME_VERSION = "1.1.0"
EXECUTABLE_NAME = "SpaceHarvest"
