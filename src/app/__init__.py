"""Application shell helpers (paths, launch)."""

from __future__ import annotations

import os
import sys


def prepare_runtime_paths() -> str:
    """Chdir to the install root and put it on ``sys.path``. Returns root."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        root = os.path.dirname(os.path.abspath(sys.executable))
        os.chdir(root)
        for path in filter(None, (meipass, root)):
            if path not in sys.path:
                sys.path.insert(0, path)
        assets = os.path.join(root, "assets")
        if meipass and not os.path.isdir(assets):
            assets = os.path.join(meipass, "assets")
        if os.path.isdir(assets):
            os.environ.setdefault("SPACE_HARVEST_ASSETS", assets)
        return root

    # src/app/__init__.py → repo root (three levels up)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def run_game(argv: list[str] | None = None) -> int:
    """Launch Space Harvest (default action of ``setup.py``)."""
    prepare_runtime_paths()
    if argv is not None:
        sys.argv = [sys.argv[0], *list(argv)]
    from src.main import main

    return int(main() or 0)
