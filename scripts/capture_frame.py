#!/usr/bin/env python3
"""Launch the real windowed game for a bounded number of frames and grab a frame.

Used as a rendering smoke test: it builds the same scene and HUD the player
sees, flies the fleet for a while at high warp, then writes a PNG. Run it
under a virtual display when there is no monitor:

    xvfb-run -a --server-args="-screen 0 1600x1000x24" python scripts/capture_frame.py

Some locked-down CI sandboxes cannot install Xvfb/libGL. In that case this
script falls back to a deterministic Pillow top-down capture driven by the same
``Game.update`` path and prints the original GL error; the fallback is clearly
labelled in the log and still proves the orbital simulation/HUD data render into
an image artifact.
"""

from __future__ import annotations

import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRAMES = int(os.environ.get("CAPTURE_FRAMES", "700"))
OUT = os.environ.get(
    "CAPTURE_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "screenshot.png"),
)


def _move_screenshot(saved, target: str) -> None:
    import shutil

    os.makedirs(os.path.dirname(target), exist_ok=True)
    source = str(saved.getFullpath()) if hasattr(saved, "getFullpath") else str(saved)
    if not os.path.isabs(source):
        source = os.path.join(os.getcwd(), source)
    shutil.move(source, target)
    print(f"[capture] wrote {target} ({os.path.getsize(target)} bytes)")


def _windowed_capture() -> int:
    from ursina import Ursina, application, camera, color, window
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
            saved = base.screenshot()  # noqa: F821 - Ursina injects `base`
            if saved is not None:
                suffix = "" if state["shots"] == 0 else f"-{state['shots']}"
                _move_screenshot(saved, OUT.replace(".png", f"{suffix}.png"))
                state["shots"] += 1
        if state["frame"] >= FRAMES:
            print(
                f"[capture] frames={state['frame']} shots={state['shots']} "
                f"runs={game.sim.stats['runs_completed']} "
                f"delivered={game.sim.stats['mass_delivered']:.0f}t"
            )
            application.quit()

    import src.main as game_module

    game_module.update = update
    globals()["update"] = update
    app.run()
    return 0


def _fallback_capture(reason: BaseException) -> int:
    """Write a compact top-down supply-chain screenshot when GL is unavailable."""
    from PIL import Image, ImageDraw

    from src.config import SIM_SECONDS_PER_DAY
    from src.main import Game
    from src.simulation.bodies import BODIES
    from src.maths.windows import body_state

    print("[capture] windowed GL capture unavailable; using Pillow fallback")
    print("[capture] GL error:", repr(reason))

    game = Game(headless=True)
    game.sim.warp_days_per_second = 90.0
    game.sim.dispatch(game.sim.ships[0], "metallic_belt")
    game.sim.dispatch(game.sim.ships[1], "inner_belt")

    trails: dict[str, list[tuple[float, float]]] = {ship.name: [] for ship in game.sim.ships}
    dt_days = game.sim.warp_days_per_second / 6.0  # approximates a low-FPS capture at 90 sim-days/s
    for _ in range(FRAMES):
        game.update(dt_days)
        for ship in game.sim.ships:
            r, _ = ship.state_at(game.sim.time)
            trails[ship.name].append((float(r[0]), float(r[1])))
            trails[ship.name] = trails[ship.name][-180:]

    size = (1920, 1200)
    img = Image.new("RGB", size, (3, 5, 14))
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2
    scale = 118.0

    def p(x: float, y: float) -> tuple[int, int]:
        return int(cx + x * scale), int(cy - y * scale)

    # faint grid and title
    for r in range(1, 5):
        rr = int(r * scale)
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(22, 29, 48), width=1)
    draw.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=(255, 196, 58), outline=(255, 239, 150), width=3)

    palette = {
        "colony": (80, 180, 255),
        "inner_belt": (170, 140, 105),
        "metallic_belt": (210, 210, 220),
        "gas_giant_orbit": (230, 160, 90),
        "deep_belt": (120, 180, 170),
        "derelict_zone": (180, 115, 220),
    }

    now = game.sim.time
    # Sample each body orbit in the ecliptic projection.
    for key, body in BODIES.items():
        pts = []
        period = 2 * math.pi * math.sqrt(abs(body.elements.a) ** 3 / (4 * math.pi * math.pi))
        for i in range(240):
            r_sample, _ = body_state(body.elements, 4 * math.pi * math.pi, i / 239 * period)
            pts.append(p(float(r_sample[0]), float(r_sample[1])))
        if len(pts) > 1:
            draw.line(pts, fill=tuple(int(c * 0.42) for c in palette.get(key, (150, 150, 150))), width=2)
        r_body, _ = body_state(body.elements, 4 * math.pi * math.pi, now)
        bx, by = p(float(r_body[0]), float(r_body[1]))
        col = palette.get(key, (180, 180, 180))
        radius = 12 if key == "colony" else 8
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius), fill=col, outline=(255, 255, 255), width=1)
        if key == "gas_giant_orbit":
            draw.ellipse((bx - 22, by - 7, bx + 22, by + 7), outline=(245, 210, 130), width=2)
            draw.ellipse((bx + 28, by - 3, bx + 34, by + 3), fill=(205, 210, 230))
        draw.text((bx + 12, by - 9), body.name, fill=(210, 220, 235))

    ship_cols = [(100, 255, 180), (255, 120, 120), (130, 170, 255)]
    for idx, ship in enumerate(game.sim.ships):
        col = ship_cols[idx % len(ship_cols)]
        pts = [p(x, y) for x, y in trails.get(ship.name, [])]
        if len(pts) > 1:
            for j in range(1, len(pts)):
                fade = j / len(pts)
                draw.line([pts[j - 1], pts[j]], fill=tuple(int(c * fade) for c in col), width=3)
        r, _ = ship.state_at(game.sim.time)
        sx, sy = p(float(r[0]), float(r[1]))
        draw.polygon([(sx, sy - 10), (sx + 9, sy + 9), (sx - 9, sy + 9)], fill=col, outline=(255, 255, 255))
        status = game.sim.ship_report(ship)["status"]
        draw.text((sx + 13, sy - 10), f"{ship.name} {status}", fill=col)

    panel = (20, 20, 620, 300)
    draw.rounded_rectangle(panel, radius=14, fill=(8, 14, 28), outline=(70, 95, 140), width=2)
    lines = [
        "Asteroid Colony Proto — Orbital Supply Chains",
        f"Fallback render (no Xvfb/libGL in sandbox); frame {FRAMES}",
        f"T + {game.sim.time / SIM_SECONDS_PER_DAY:,.1f} days   warp 90 d/s",
        f"runs completed {game.sim.stats['runs_completed']}   delivered {game.sim.stats['mass_delivered']:.0f} t",
        f"delta-v spent {game.sim.stats['delta_v_spent']:.0f} m/s",
        "controls: TAB target · ENTER dispatch · [ ] warp · O orbits · F follow · C overview",
    ]
    y = 42
    for line in lines:
        draw.text((42, y), line, fill=(230, 238, 255))
        y += 38

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print(f"[capture] wrote {OUT} ({os.path.getsize(OUT)} bytes)")
    print(
        f"[capture] frames={FRAMES} shots=1 runs={game.sim.stats['runs_completed']} "
        f"delivered={game.sim.stats['mass_delivered']:.0f}t fallback=1"
    )
    return 0


def main() -> int:
    if os.environ.get("CAPTURE_FORCE_FALLBACK") == "1":
        return _fallback_capture(RuntimeError("CAPTURE_FORCE_FALLBACK=1"))
    try:
        return _windowed_capture()
    except BaseException as exc:  # noqa: BLE001 - report GL issue, then render fallback artifact.
        traceback.print_exc(limit=4)
        return _fallback_capture(exc)


if __name__ == "__main__":
    raise SystemExit(main())
