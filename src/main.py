#!/usr/bin/env python3
"""Asteroid Colony Proto -- orbital supply chains.

Entry point. Runs the patched-conic simulation from ``src.simulation`` inside a
Ursina window and hands every completed delivery to the existing
``asteroid-colony`` economy (``src/game/logistics.py``), so colony storage,
research points and score all respond to what the freighters bring back.

    python -m src.main                    # play
    python -m src.main --headless         # same loop, no window (self-test / CI)
    python -m src.main --headless --sim-days 4000

The ``--headless`` path drives exactly the same ``Game.update`` as the windowed
one, which is what lets the whole game be verified without a display.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import (  # noqa: E402
    REDISPATCH_SCAN_DAYS,
    SHIP_REFUEL_ENERGY_PER_MS,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from src.simulation.bodies import TRADE_TARGETS  # noqa: E402
from src.config import SIM_SECONDS_PER_DAY  # noqa: E402
from src.simulation.orbital_sim import OrbitalSimulation  # noqa: E402

# The vendored upstream game provides the colony economy.
from src.game import logistics as colony_logistics  # noqa: E402
from src.game import state as colony_state  # noqa: E402


class Colony:
    """Bridges the orbital simulation into the existing colony economy."""

    def __init__(self):
        self.state = colony_state.initial_state()

    def receive(self, cargo: dict[str, float]) -> dict:
        """Store a freighter's delivery using the upstream storage rules."""
        payload = {key: float(amount) for key, amount in cargo.items() if amount > 0}
        if not payload:
            return {"stored": {}, "overflow": {}}
        stored, overflow = colony_logistics.store(self.state, payload)
        self.state["research_points"] = float(self.state.get("research_points", 0.0)) + 0.25 * sum(stored.values())
        return {"stored": stored, "overflow": overflow}

    def summary(self) -> dict:
        return colony_logistics.summary(self.state)


class Game:
    """Owns the simulation, the colony and -- when windowed -- the 3-D scene."""

    def __init__(self, headless: bool = False, ship_names: tuple[str, ...] = ("Kestrel", "Petrel")):
        self.headless = headless
        self.sim = OrbitalSimulation(ship_names=ship_names)
        self.colony = Colony()
        self.scene = None
        self.hud = None
        self.follow_target: str | None = None
        self.frames = 0
        self.deliveries_booked = 0
        self._message = ""
        self._message_until = 0.0

    # -- messaging -----------------------------------------------------------
    def say(self, text: str, seconds: float = 6.0) -> None:
        self._message = text
        self._message_until = time.time() + seconds
        print(f"[game] {text}")

    def _current_message(self) -> str:
        return self._message if time.time() < self._message_until else ""

    # -- scene ---------------------------------------------------------------
    def build_scene(self, ursina_scene) -> None:
        """Create the 3-D network view and the HUD. Windowed mode only."""
        from src.entities.orbital_scene import OrbitalScene
        from src.ui.orbital_hud import OrbitalHUD

        self.scene = OrbitalScene(parent=ursina_scene)
        self.hud = OrbitalHUD(TRADE_TARGETS)
        self.set_camera_preset("network")

    def set_camera_preset(self, preset: str) -> None:
        from ursina import Vec3, camera

        presets = {"network": Vec3(0, 46, -52), "close": Vec3(0, 12, -18), "top": Vec3(0, 78, -1)}
        if preset in presets:
            camera.position = presets[preset]
            camera.look_at(Vec3(0, 0, 0))
            self.follow_target = None

    def cycle_follow(self) -> None:
        """Rotate camera tracking between ships and the free network view."""
        names = [ship.name for ship in self.sim.ships]
        if not names:
            return
        if self.follow_target is None:
            self.follow_target = names[0]
        else:
            index = names.index(self.follow_target) + 1
            self.follow_target = names[index] if index < len(names) else None
        if self.follow_target is None:
            self.set_camera_preset("network")
            self.say("Camera free (network view).")
        else:
            self.say(f"Camera following {self.follow_target}.")

    def update_camera(self) -> None:
        if self.follow_target is None or self.scene is None:
            return
        from ursina import camera

        ship = self.scene.ships.get(self.follow_target)
        if ship is None:
            return
        offset = camera.position - ship.position
        distance = offset.length()
        if distance > 26.0 or distance < 6.0:
            offset = offset.normalized() * 14.0 if distance > 1e-3 else (0, 6, -14)
        camera.position = ship.position + offset
        camera.look_at(ship.position)

    # -- actions -------------------------------------------------------------
    def dispatch_selected(self) -> None:
        if self.hud is None:
            return
        target = self.hud.selected_target()
        idle = next((ship for ship in self.sim.ships if ship.name not in self.sim.missions), None)
        if idle is None:
            self.say("Every freighter is already flying a mission.")
            return
        _, message = self.sim.dispatch(idle, target)
        self.say(message, seconds=8.0)

    # -- main loop -----------------------------------------------------------
    def update(self, dt_days: float) -> None:
        """Advance one frame by ``dt_days`` of simulation time.

        Callers pass seconds times the warp rate, so windowed and headless
        modes run the identical code path.
        """
        self.frames += 1
        self.sim.step(dt_days)
        self._book_deliveries()
        self._refuel_and_redispatch(dt_days)

        if self.scene is not None:
            self.scene.update(self.sim)
            self.update_camera()
        if self.hud is not None:
            self.hud.update(self.sim, self.colony.summary(), self._current_message())

    def _book_deliveries(self) -> None:
        """Drain completed deliveries into the colony economy."""
        while self.sim.pending_deliveries:
            delivery = self.sim.pending_deliveries.pop(0)
            result = self.colony.receive(delivery.cargo)
            stored = sum(result["stored"].values())
            overflow = sum(result["overflow"].values())
            self.deliveries_booked += 1
            if stored > 0:
                self.say(
                    f"{delivery.ship} delivered {stored:,.0f} t from {delivery.body}"
                    + (f" ({overflow:,.0f} t lost to full storage)" if overflow > 0 else ""),
                    seconds=8.0,
                )


    def _refuel_and_redispatch(self, dt_days: float) -> None:
        """Top up docked freighters from colony energy and send them back out.

        Both halves are what keep the supply chain alive: without refuelling a
        fleet grounds itself after two runs, and without cost-aware dispatch a
        ship will accept a mission it cannot return from.
        """
        granted = self.sim.refuel_docked_fleet(dt_days)
        if granted > 0.0:
            energy = self.colony.state.get("resources", {})
            cost = granted * SHIP_REFUEL_ENERGY_PER_MS
            energy["energy"] = max(0.0, energy.get("energy", 0.0) - cost)

        # Re-pricing the network means solving Lambert grids, so the scan is
        # throttled. Ships already flying are unaffected.
        if self.sim.time < self.sim._next_scan_time:
            return
        if not any(
            ship.name not in self.sim.missions and ship.origin == "colony"
            for ship in self.sim.ships
        ):
            return
        self.sim._next_scan_time = self.sim.time + REDISPATCH_SCAN_DAYS * SIM_SECONDS_PER_DAY

        for ship in self.sim.ships:
            if ship.name in self.sim.missions or ship.origin != "colony":
                continue
            options = self.sim.affordable_targets(ship)
            if not options:
                continue
            # Options come back cheapest first; send the idle freighter on the
            # most expensive run it can still finish, so the propellant budget
            # buys the highest-value cargo.
            self.sim.dispatch(ship, options[-1][0])


def run_headless(sim_days: float, frames_per_day: int = 4, verbose: bool = True) -> Game:
    """Drive the game loop with no window; used by the self-test and CI."""
    game = Game(headless=True)
    dt_days = 1.0 / frames_per_day
    game.sim.warp_days_per_second = 1.0  # dt already carries the time step

    # Send both freighters out so the loop has real work to do.
    game.sim.dispatch(game.sim.ships[0], "inner_belt")
    game.sim.dispatch(game.sim.ships[1], "metallic_belt")

    for _ in range(int(sim_days * frames_per_day)):
        game.update(dt_days)

    if verbose:
        print(f"[headless] {game.frames} frames over {sim_days:,.0f} sim-days")
        for report in game.sim.fleet_report():
            print(f"  {report['name']:<8}{report['status']:<9}{report['at']:<22}{report['delta_v_left']:>8,.0f} m/s left")
        stats = game.sim.stats
        print(f"  runs completed : {stats['runs_completed']}")
        print(f"  mass delivered : {stats['mass_delivered']:,.0f} t")
        print(f"  delta-v spent  : {stats['delta_v_spent']:,.0f} m/s")
        print(f"  deliveries into colony economy: {game.deliveries_booked}")
        print(f"  colony storage : {game.colony.summary()}")
        print(f"  research points: {game.colony.state.get('research_points', 0.0):,.1f}")
    return game


def run_windowed() -> None:
    from ursina import Ursina, camera, color, window
    from ursina import scene as ursina_scene
    from ursina import application

    # Ursina is a singleton and ``run`` is an *instance* method, so the
    # application object has to be kept; ``application.run()`` does not exist.
    app = Ursina(title=WINDOW_TITLE, size=WINDOW_SIZE, borderless=False)
    window.color = color.black

    game = Game(headless=False)
    game.build_scene(ursina_scene)
    camera.orthographic = False
    camera.fov = 55

    import src.main as this_module

    def update():  # Ursina calls this every frame
        game.update(time.dt * game.sim.warp_days_per_second)

    def input(key):
        if key == "escape":
            application.quit()
        elif key == "tab" and game.hud is not None:
            game.hud.cycle_target(1)
            game.say(f"Target: {game.hud.selected_target()}")
        elif key == "enter":
            game.dispatch_selected()
        elif key == "o" and game.scene is not None:
            game.scene.set_orbits_visible(not game.scene.orbits_visible)
        elif key == "f":
            game.cycle_follow()
        elif key == "c":
            game.set_camera_preset("network")
        elif key == "[":
            game.sim.cycle_warp(-1)
        elif key == "]":
            game.sim.cycle_warp(1)
        elif key == "scroll up":
            camera.position *= 0.9
        elif key == "scroll down":
            camera.position *= 1.1

    # Ursina discovers the loop and input handler through this module's globals.
    this_module.update = update
    this_module.input = input
    globals()["update"] = update
    globals()["input"] = input

    app.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Asteroid Colony Proto - orbital supply chains")
    parser.add_argument("--headless", action="store_true", help="run the loop with no window")
    parser.add_argument("--sim-days", type=float, default=900.0, help="sim days for --headless")
    parser.add_argument("--quiet", action="store_true", help="suppress the headless report")
    args = parser.parse_args()

    if args.headless:
        run_headless(args.sim_days, verbose=not args.quiet)
        return 0
    run_windowed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
