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
SHIP_REFUEL_RATE = 22.0
SHIP_REFUEL_ENERGY_PER_MS = 0.004  # colony energy units per m/s restored
SHIP_ISP = 3200.0            # s, electric propulsion flavour

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
