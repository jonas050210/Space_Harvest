"""Colony-economy constants shared with the orbital shell.

Only the keys the live game reads remain. The full upstream builder catalogue
lived here once; it was trimmed when Space Harvest became the product.

Canonical values now live in ``src.config`` - this module re-exports for
backward compatibility so ``from src.colony.config import DEFAULT_DIFFICULTY``
still works.
"""

from __future__ import annotations

try:
    from src.config import DEFAULT_DIFFICULTY  # noqa: F401
except Exception:
    DEFAULT_DIFFICULTY = "medium"
