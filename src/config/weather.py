"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- space weather: solar flares and debris seasons --------------------------
# Global, deterministic, ticked by the operations step. Only ships in flight
# are exposed; docked ships sit inside the colony's shielding.
FLARE_QUIET_DAYS_RANGE = (120.0, 420.0)  # quiet-time draw before the next cycle
FLARE_WARNING_DAYS = 6.0                 # HUD-visible warning before it hits
FLARE_DURATION_DAYS_RANGE = (2.0, 5.0)
FLARE_WEAR_PCT_PER_DAY = 1.2             # extra hull wear for ships in flight
FLARE_MORALE_DRAIN_PER_DAY = 0.8         # crews hate riding out a storm
# Solar exposure by body (ops layer): ships flying to/from a listed body take
# multiplied flare wear — the price of skimming the sun. 1.0 is the network
# default; Sungrazer Field is the furnace that makes helium-3 a hazard pay.
FLARE_EXPOSURE_BY_BODY = {
    "sungrazer": 2.5,
}
DEBRIS_SEASON_PERIOD_DAYS = 300.0        # roughly periodic debris seasons
DEBRIS_SEASON_DURATION_DAYS = 40.0
DEBRIS_WEAR_PCT_PER_DAY = 0.35           # micrometeorite sandblasting in flight

