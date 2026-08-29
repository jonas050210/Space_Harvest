"""Auto-split from __init__.py - see __init__.py for aggregation."""

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

