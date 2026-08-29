"""Backward compat shim - routing constants moved to routing.py.

This file re-exports for old imports ``from src.config.routes import ...``.
New code should use ``from src.config.routing import ...`` or ``from src.config import ...``.
"""
from __future__ import annotations
from .routing import *  # noqa: F401,F403
