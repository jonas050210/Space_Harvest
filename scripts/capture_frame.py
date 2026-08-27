#!/usr/bin/env python3
"""Launch the real windowed game for a bounded number of frames and grab a frame.

Used as a rendering smoke test: it builds the same scene and HUD the player
sees, flies the fleet for a while at high warp, then writes a PNG. Run it
under a virtual display when there is no monitor:

    xvfb-run -a --server-args="-screen 0 1600x1000x24" python scripts/capture_frame.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRAMES = int(os.environ.get("CAPTURE_FRAMES", "700"))
OUT = os.environ.get("CAPTURE_OUT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "screenshot.png"))


def main() -> int:
    from ursina import Ursina, application, camera, color, invoke, window
    from ursina import scene as ursina_scene

    from src.config import WINDOW_SIZE, WINDOW_TITLE
    from src.main import Game

    app = Ursina(title=WINDOW_TITLE, size=WINDOW_SIZE, borderless=False)
    window.color = color.black

    game = Game(headless=False)
    game.build_scene(ursina_scene)
    camera.orthographic = False
    camera.fov = 55

    # Give the fleet work so the screenshot shows ships on transfer arcs.
    game.sim.warp_days_per_second = 90.0
    game.sim.dispatch(game.sim.ships[0], "metallic_belt")
    game.sim.dispatch(game.sim.ships[1], "inner_belt")

    state = {"frame": 0, "shots": 0}

    def update():
        import time as _time

        state["frame"] += 1
        game.update(_time.dt * game.sim.warp_days_per_second)
        if state["frame"] in (220, FRAMES):
            # base.screenshot() writes the image itself and returns the
            # Filename it used; move it somewhere predictable.
            saved = base.screenshot()  # noqa: F821 - Ursina injects `base`
            if saved is not None:
                import shutil

                suffix = "" if state["shots"] == 0 else f"-{state['shots']}"
                target = OUT.replace(".png", f"{suffix}.png")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                source = str(saved.getFullpath()) if hasattr(saved, "getFullpath") else str(saved)
                if not os.path.isabs(source):
                    source = os.path.join(os.getcwd(), source)
                shutil.move(source, target)
                print(f"[capture] wrote {target} ({os.path.getsize(target)} bytes)")
                state["shots"] += 1
        if state["frame"] >= FRAMES:
            print(f"[capture] frames={state['frame']} shots={state['shots']} "
                  f"runs={game.sim.stats['runs_completed']} "
                  f"delivered={game.sim.stats['mass_delivered']:.0f}t")
            application.quit()

    import src.main as game_module

    game_module.update = update
    globals()["update"] = update
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
