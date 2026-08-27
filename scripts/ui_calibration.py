#!/usr/bin/env python3
"""Calibration helper: draw known UI primitives and screenshot them.

Run under xvfb. The output tells us how camera.ui maps x to pixels and how
``color.rgba`` interprets its arguments in Ursina 8.3.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import Entity, Text, Vec3, application, camera, color, window
from ursina import Ursina

app = Ursina(title="cal", size=(1440, 900), borderless=False)
window.color = color.black

# Vertical reference bars at known x positions: -1.0, -0.5, 0.0, 0.5, 1.0
for x in (-1.0, -0.5, 0.0, 0.5, 1.0):
    Entity(parent=camera.ui, model="quad", scale=(0.01, 0.9), position=Vec3(x, 0, 0),
           color=color.rgb(1, 0, 0))

# A dark panel using the two plausible alpha conventions.
Entity(parent=camera.ui, model="quad", scale=(0.3, 0.3), position=Vec3(-0.5, 0.35, 0),
       color=color.rgba(12, 16, 26, 0.86))
Entity(parent=camera.ui, model="quad", scale=(0.3, 0.3), position=Vec3(-0.5, 0.0, 0),
       color=color.rgba(12 / 255, 16 / 255, 26 / 255, 220))
Entity(parent=camera.ui, model="quad", scale=(0.3, 0.3), position=Vec3(-0.5, -0.35, 0),
       color=color.Color(0.05, 0.06, 0.1, 0.86))

Text(text="x=-1.0 red bar", parent=camera.ui, position=Vec3(-0.98, -0.47, 0), scale=0.8,
     color=color.lime, origin=(-0.5, 0))
Text(text="panel alpha 0.86 (0-255 arg)", parent=camera.ui, position=Vec3(-0.64, 0.35, -1), scale=0.7)
Text(text="panel rgba(0-1, 220)", parent=camera.ui, position=Vec3(-0.64, 0.0, -1), scale=0.7)
Text(text="panel Color(0-1, a=0.86)", parent=camera.ui, position=Vec3(-0.64, -0.35, -1), scale=0.7)

state = {"frame": 0}

def update():
    state["frame"] += 1
    if state["frame"] == 60:
        saved = base.screenshot()  # noqa: F821
        import shutil
        target = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "calibration.png")
        source = str(saved.getFullpath()) if hasattr(saved, "getFullpath") else str(saved)
        if not os.path.isabs(source):
            source = os.path.join(os.getcwd(), source)
        shutil.move(source, target)
        print("[cal] wrote", target)
    if state["frame"] == 70:
        application.quit()

globals()["update"] = update
app.run()
