"""Global constants for the orbital supply-chain prototype.

This package was split from a monolithic __init__.py (887 lines) into
focused submodules for maintainability. This file re-exports everything
so ``from src.config import SHIP_CLASSES`` keeps working.

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

from .units import *  # noqa: F401,F403
from .ships import *  # noqa: F401,F403
from .mining import *  # noqa: F401,F403
from .market import *  # noqa: F401,F403
from .crew import *  # noqa: F401,F403
from .weather import *  # noqa: F401,F403
from .contracts import *  # noqa: F401,F403
from .life import *  # noqa: F401,F403
from .parts import *  # noqa: F401,F403
from .campaign import *  # noqa: F401,F403
from .depot import *  # noqa: F401,F403
from .refinery import *  # noqa: F401,F403
from .progression import *  # noqa: F401,F403
from .stations import *  # noqa: F401,F403
from .routing import *  # noqa: F401,F403
from .difficulty import *  # noqa: F401,F403
from .quality import *  # noqa: F401,F403
from .swarms import *  # noqa: F401,F403
from .game import *  # noqa: F401,F403

# Explicit re-export list for linters / IDEs - populated dynamically
# All caps constants from submodules are considered public API
from .validation import validate, validate_or_raise  # noqa: F401
