"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


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


