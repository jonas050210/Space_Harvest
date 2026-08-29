"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


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

