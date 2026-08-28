#!/usr/bin/env python3
"""Space Harvest launcher.

Used by the windowed game and by PyInstaller (``setup.py --build``).
Frozen builds resolve assets next to the executable.
"""

from __future__ import annotations

import os
import sys


def _prepare_paths() -> None:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile extracts to _MEIPASS; onedir sits beside the exe.
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        root = os.path.dirname(sys.executable)
        os.chdir(root)
        if base not in sys.path:
            sys.path.insert(0, base)
        if root not in sys.path:
            sys.path.insert(0, root)
        # Ensure asset lookups find the bundled textures.
        assets = os.path.join(root, "assets")
        if not os.path.isdir(assets):
            assets = os.path.join(base, "assets")
        if os.path.isdir(assets):
            os.environ.setdefault("SPACE_HARVEST_ASSETS", assets)
    else:
        root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(root)
        if root not in sys.path:
            sys.path.insert(0, root)


def main() -> int:
    _prepare_paths()
    from src.main import main as game_main

    return int(game_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
