"""Compatibility shim — the report importer lives in ``app/utils/``.

The UI (SYSTEM page, Phase 25) imports the importer from the app
package; scripts and tests keep importing from here so nothing breaks.
Module-level ``__getattr__`` (PEP 562) forwards every attribute to the
real implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.utils.report_importer as _impl  # noqa: E402


def __getattr__(name: str):
    return getattr(_impl, name)
