#!/usr/bin/env python3
"""Redirect — capture lives in tools/capture_frame.py."""
import runpy
import pathlib
runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "capture_frame.py"), run_name="__main__")
