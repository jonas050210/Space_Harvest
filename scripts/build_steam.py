#!/usr/bin/env python3
"""Redirect — use packaging/build_exe.py or setup.py --build."""
import runpy, pathlib
runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1] / "packaging" / "build_exe.py"), run_name="__main__")
