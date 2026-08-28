#!/usr/bin/env python3
"""Launch the real windowed game for a bounded number of frames and grab a frame.

Used as a rendering smoke test: it builds the same scene and HUD the player
sees, flies the fleet for a while at high warp, then writes a PNG. Run it
under a virtual display when there is no monitor:

    xvfb-run -a --server-args="-screen 0 1600x1000x24" python tools/capture_frame.py

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
    # A lively mid-game moment: ~1,000 days in, fleet busy, colony funded.
    dt_days = 2.0
    next_sale = 90.0 * SIM_SECONDS_PER_DAY
    depot_built = False
    for _ in range(FRAMES):
        game.update(dt_days)
        if game.sim.time >= next_sale:
            next_sale += 90.0 * SIM_SECONDS_PER_DAY
            game.sell_all()
        if not depot_built and game.credits > 8000.0:
            game.build_depot_selected()   # headless default: the deep belt
            depot_built = True
        for ship in game.sim.ships:
            r, _ = ship.state_at(game.sim.time)
            trails[ship.name].append((float(r[0]), float(r[1])))
            trails[ship.name] = trails[ship.name][-70:]

    from PIL import ImageFont


    def _font(size: int):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    size = (1920, 1200)
    img = Image.new("RGB", size, (4, 5, 12))
    draw = ImageDraw.Draw(img)

    # -- starfield backdrop (the real generated skybox) -----------------------
    stars_path = os.path.join("assets", "textures", "game", "skybox_stars.png")
    if os.path.isfile(stars_path):
        stars = Image.open(stars_path).convert("RGB").resize(size)
        img = Image.blend(img, stars, alpha=0.9)
        draw = ImageDraw.Draw(img)

    cx, cy = size[0] // 2, size[1] // 2
    scale = 118.0

    def p(x: float, y: float) -> tuple[int, int]:
        return int(cx + x * scale), int(cy - y * scale)

    now = game.sim.time

    # -- sun with layered glow sprites ----------------------------------------
    glow_path = os.path.join("assets", "textures", "game", "sun_glow.png")
    if os.path.isfile(glow_path):
        for glow_px, opacity in ((340, 0.85), (720, 0.45)):
            sprite = Image.open(glow_path).convert("RGBA").resize((glow_px, glow_px))
            alpha = sprite.split()[3].point(lambda a, o=opacity: int(a * o))
            sprite.putalpha(alpha)
            img.paste(sprite, (cx - glow_px // 2, cy - glow_px // 2), sprite)
        draw = ImageDraw.Draw(img)
    draw.ellipse((cx - 20, cy - 20, cx + 20, cy + 20), fill=(255, 214, 130),
                 outline=(255, 244, 200), width=3)

    # -- asteroid belt scatter -------------------------------------------------
    import random as _random

    rng = _random.Random(11)
    for _ in range(260):
        a = rng.uniform(1.32, 2.28)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        ax, ay = p(a * math.cos(angle), a * math.sin(angle))
        shade = rng.randint(70, 120)
        r_px = rng.randint(1, 2)
        draw.ellipse((ax - r_px, ay - r_px, ax + r_px, ay + r_px), fill=(shade, shade, shade + 8))

    # -- orbits, then textured planets ------------------------------------------
    for key, body in BODIES.items():
        if key == "nix":
            continue
        rgb = tuple(int(c * 255) for c in body.palette)
        pts = []
        period = 2 * math.pi * math.sqrt(abs(body.elements.a) ** 3 / (4 * math.pi * math.pi))
        for i in range(240):
            r_sample, _ = body_state(body.elements, 4 * math.pi * math.pi, i / 239 * period)
            pts.append(p(float(r_sample[0]), float(r_sample[1])))
        if len(pts) > 1:
            draw.line(pts, fill=tuple(int(c * 0.40) for c in rgb), width=2)

    for key, body in list(game.sim.bodies.items()):
        if key == "nix":
            continue
        r_body, _ = body_state(body.elements, 4 * math.pi * math.pi, now)
        bx, by = p(float(r_body[0]), float(r_body[1]))
        diameter = int(30 + 44 * body.render_scale)
        if key == "comet_vigil":
            # Anti-sunward tail, brightness by distance.
            dist = math.hypot(r_body[0], r_body[1])
            strength = max(0.0, min(1.0, 1.6 / max(0.9, dist) ** 1.6))
            if strength > 0.02:
                ux, uy = -r_body[0] / dist, -r_body[1] / dist  # toward the sun
                tx, ty = p(float(r_body[0]) - ux * 0.9, float(r_body[1]) - uy * 0.9)
                draw.line((bx, by, tx, ty), fill=(120, 190, 235), width=max(2, int(9 * strength)))
                draw.line((bx, by, tx, ty), fill=(190, 225, 250), width=max(1, int(3 * strength)))
        tex_path = os.path.join("assets", "textures", "game", f"{key}.png")
        if os.path.isfile(tex_path):
            tex = Image.open(tex_path).convert("RGB").resize((diameter, diameter))
            mask = Image.new("L", (diameter, diameter), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
            img.paste(tex, (bx - diameter // 2, by - diameter // 2), mask)
            draw = ImageDraw.Draw(img)
        else:
            rgb = tuple(int(c * 255) for c in body.palette)
            draw.ellipse((bx - diameter // 2, by - diameter // 2,
                          bx + diameter // 2, by + diameter // 2), fill=rgb)
        if key == "gas_giant_orbit":
            ring_box = (bx - int(diameter * 1.05), by - int(diameter * 0.30),
                        bx + int(diameter * 1.05), by + int(diameter * 0.30))
            draw.ellipse(ring_box, outline=(235, 205, 245), width=3)
        # name tag pill
        font_tag = _font(17)
        tw = draw.textlength(body.name, font=font_tag)
        pill = (bx - tw / 2 - 10, by - diameter // 2 - 34,
                bx + tw / 2 + 10, by - diameter // 2 - 6)
        draw.rounded_rectangle(pill, radius=9, fill=(8, 12, 22))
        draw.text((pill[0] + 10, pill[1] + 4), body.name, font=font_tag, fill=(205, 232, 255))

    # -- ships with fading trails -------------------------------------------------
    class_cols = {"scout": (120, 210, 255), "freighter": (235, 235, 245),
                  "refinery": (255, 214, 140), "hauler": (255, 160, 160)}
    for ship in game.sim.ships:
        col = class_cols.get(game.sim.ship_class.get(ship.name), (200, 220, 255))
        pts = [p(x, y) for x, y in trails.get(ship.name, [])]
        if len(pts) > 1:
            for j in range(1, len(pts)):
                fade = j / len(pts)
                draw.line([pts[j - 1], pts[j]], fill=tuple(int(c * fade * 0.8) for c in col), width=3)
        r, _ = ship.state_at(game.sim.time)
        sx, sy = p(float(r[0]), float(r[1]))
        status = game.sim.ship_report(ship)["status"]
        thrusting = status in ("outbound", "inbound", "pending")
        if thrusting:
            draw.ellipse((sx - 14, sy - 14, sx + 14, sy + 14), outline=col, width=2)
        draw.polygon([(sx, sy - 10), (sx + 9, sy + 9), (sx - 9, sy + 9)], fill=col,
                     outline=(255, 255, 255))
        draw.text((sx + 13, sy - 10), f"{ship.name} {status}", font=_font(15), fill=col)

    # -- HUD: mission panel (left) and colony panel (right) -----------------------
    def panel(box, title, lines, accent=(90, 140, 210)):
        draw.rounded_rectangle(box, radius=14, fill=(8, 13, 26), outline=accent, width=2)
        draw.text((box[0] + 20, box[1] + 14), title, font=_font(21), fill=(120, 200, 255))
        y = box[1] + 52
        for line in lines:
            draw.text((box[0] + 22, y), line, font=_font(16), fill=(226, 234, 250))
            y += 26

    days = game.sim.time / SIM_SECONDS_PER_DAY
    fleet_lines = []
    for report in game.sim.fleet_report():
        hull = game.sim.hull.get(report["name"], 100.0)
        fleet_lines.append(
            f"{report['name']:<8} {report['status']:<9} {report['delta_v_left']:>6,.0f} m/s  H{hull:.0f}%"
        )
    game._update_windows_board()
    board_lines = ["NEXT WINDOWS"]
    for name, wait, is_open in game._windows_board[:6]:
        board_lines.append(f"GO  {name}" if is_open else f"    {name:<20}{wait:>5,.0f} d")
    panel((24, 24, 660, 400), "ORBITAL LOGISTICS", [
        f"Mission day {days:,.0f}   (year {days / 365.25:.2f})",
        f"runs {game.sim.stats['runs_completed']}   delivered {game.sim.stats['mass_delivered']:,.0f} t",
        *fleet_lines,
        *([""] + board_lines),
    ])
    resources = game.colony.state["resources"]
    prices = ", ".join(f"{res} {game.market.price(res):.1f}" for res in ("iron", "silver", "gold"))
    right_lines = [
        f"treasury {game.credits:,.0f} cr",
        f"market: {prices} cr/t",
        f"ice {resources.get('ice', 0):.0f} t   O2 {resources.get('oxygen', 0):.0f}   food {resources.get('food', 0):.0f}",
        f"crew morale {game.sim.fleet_morale():.0f}/100",
        f"depots: {len(game.sim.depots)}   mining: {game.sim.mining_mode}",
    ]
    panel((size[0] - 560, 24, size[0] - 24, 268), "COLONY", right_lines, accent=(70, 110, 90))

    # -- toasts + title topline ------------------------------------------------------
    recent = [text for _, text in reversed(game.toasts)][:3]
    y = 40
    for text in recent:
        tw = draw.textlength(text, font=_font(17))
        box = (size[0] / 2 - tw / 2 - 14, y - 6, size[0] / 2 + tw / 2 + 14, y + 24)
        draw.rounded_rectangle(box, radius=10, fill=(10, 16, 30))
        draw.text((box[0] + 14, y), text, font=_font(17), fill=(210, 235, 255))
        y += 40
    title_font = _font(40)
    title = "ORBITAL SUPPLY CHAINS"
    tw = draw.textlength(title, font=title_font)
    draw.text((size[0] / 2 - tw / 2 + 2, size[1] - 74 + 2), title, font=title_font, fill=(20, 40, 70))
    draw.text((size[0] / 2 - tw / 2, size[1] - 76), title, font=title_font, fill=(110, 200, 255))
    sub = "fallback render (no GL in sandbox) - the real game is 3-D Ursina"
    draw.text((size[0] / 2 - draw.textlength(sub, font=_font(15)) / 2, size[1] - 30),
              sub, font=_font(15), fill=(140, 160, 190))

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
