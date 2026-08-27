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
    LIFE_ELECTROLYSIS_ENERGY_PER_O2,
    LIFE_ELECTROLYSIS_WATER_PER_O2,
    LIFE_FOOD_PER_CREW_DAY,
    LIFE_HYDROPONICS_ENERGY_PER_FOOD,
    LIFE_HYDROPONICS_WATER_PER_FOOD,
    LIFE_ICE_HORIZON_DAYS,
    LIFE_ICE_MELT_RATE_PER_DAY,
    LIFE_ICE_PREMIUM_MAX,
    LIFE_ICE_RESERVE_T,
    LIFE_ICE_TO_WATER_YIELD,
    LIFE_LOW_STOCK_FRACTION,
    LIFE_OXYGEN_PER_CREW_DAY,
    LIFE_SHORTAGE_MORALE_DRAIN_PER_DAY,
    LIFE_SOLAR_ENERGY_PER_DAY,
    LIFE_START_FOOD,
    LIFE_START_OXYGEN,
    LIFE_START_WATER,
    LIFE_WATER_PER_CREW_DAY,
    MARKET_BASE_PRICES,
    REDISPATCH_SCAN_DAYS,
    SHIP_CLASSES,
    SHIP_REFUEL_ENERGY_PER_MS,
    START_CREDITS,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from src.simulation.bodies import TRADE_TARGETS  # noqa: E402
from src.config import SIM_SECONDS_PER_DAY  # noqa: E402
from src.mining import assay_lines, plan_extraction  # noqa: E402
from src.market import Contracts, Market  # noqa: E402
from src.operations import OpsSimulation  # noqa: E402
from src.simulation.orbital_sim import OrbitalSimulation  # noqa: E402

# The vendored upstream game provides the colony economy -- and its JSON
# savegame slots are reused verbatim for the orbital layer's saves.
from src.game import logistics as colony_logistics  # noqa: E402
from src.game import savegame as colony_savegame  # noqa: E402
from src.game import state as colony_state  # noqa: E402

BUY_MENU = ("scout", "freighter", "refinery", "hauler")
CREDITS_HISTORY_POINTS = 240
CREDITS_HISTORY_SAMPLE_DAYS = 2.0


class Colony:
    """Bridges the orbital simulation into the existing colony economy."""

    def __init__(self):
        self.state = colony_state.initial_state()
        # Life-support stocks live alongside the upstream resources; the
        # upstream game never touches these keys, the orbital game ticks them.
        self.state["resources"]["oxygen"] = LIFE_START_OXYGEN
        self.state["resources"]["food"] = LIFE_START_FOOD
        self.state["resources"]["water"] = LIFE_START_WATER

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
        # OpsSimulation wraps the verified orbital sim with fleet classes,
        # hull wear and mining; the astrodynamics core is untouched.
        self.sim = OpsSimulation(ship_names=ship_names)
        self.colony = Colony()
        self.market = Market()
        self.contracts = Contracts(self.market)
        self.credits = START_CREDITS
        self.auto_repair = True
        self.credits_history: list[tuple[float, float]] = []
        # Fraction of the colony's power budget in use; drives the ambient hum.
        self.power_load = 0.2
        self._life_shortage_flag = False
        # One-shot flags the flight-orientation checklist watches.
        self.tutorial_text = ""
        self._tut = {"dispatched": False, "sold": False, "drilled": False,
                     "bought": False, "saved": False, "done": False}
        # Alert edges, so tones play once per incident instead of every frame.
        self._alert_edges = {"flare": False, "hull": False, "shortage": False}
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
        self.sim.recover_mines(dt_days)
        self.market.update(dt_days)
        self._tick_life_support(dt_days)
        self._tick_contracts()
        self._sample_credits_history()
        self._book_deliveries()
        self._refuel_and_redispatch(dt_days)
        self._tick_tutorial()

        if self.scene is not None:
            self.scene.update(self.sim)
            self.update_camera()
        if self.hud is not None:
            self.hud.update(self.sim, self.colony.summary(), self._current_message(),
                            extra=self._ops_hud_data())

    def _sample_credits_history(self) -> None:
        days = self.sim.time / SIM_SECONDS_PER_DAY
        if self.credits_history and days - self.credits_history[-1][0] < CREDITS_HISTORY_SAMPLE_DAYS:
            return
        self.credits_history.append((days, self.credits))
        if len(self.credits_history) > CREDITS_HISTORY_POINTS:
            del self.credits_history[: len(self.credits_history) - CREDITS_HISTORY_POINTS]

    def _book_deliveries(self) -> None:
        """Drain completed deliveries into the colony economy."""
        while self.sim.pending_deliveries:
            delivery = self.sim.pending_deliveries.pop(0)
            result = self.colony.receive(delivery.cargo)
            stored = sum(result["stored"].values())
            overflow = sum(result["overflow"].values())
            self.deliveries_booked += 1
            for contract in self.contracts.register_delivery(delivery.cargo):
                reward = self.contracts.complete(contract)
                self.credits += reward
                self.say(
                    f"Order filled: {contract.tonnes:,.0f} t {contract.resource} for "
                    f"{contract.faction} -- {reward:,.0f} cr.",
                    seconds=8.0,
                )
            if stored > 0:
                self.say(
                    f"{delivery.ship} delivered {stored:,.0f} t from {delivery.body}"
                    + (f" ({overflow:,.0f} t lost to full storage)" if overflow > 0 else ""),
                    seconds=8.0,
                )


    # -- market & fleet actions ----------------------------------------------
    def sell_all(self) -> None:
        """Sell marketable ore at today's prices, honouring the ice reserve.

        The colonists eat ice (melted into water for oxygen and food), so the
        reserve is never put on the market. Standing with Earth factions moves
        the prices; a sale also pays the fleet, which crews appreciate.
        """
        resources = self.colony.state.get("resources", {})
        lots: dict[str, float] = {}
        for res, amount in resources.items():
            if res not in MARKET_BASE_PRICES or amount < 1.0:
                continue
            if res == "ice":
                amount = max(0.0, amount - LIFE_ICE_RESERVE_T)
            if amount >= 1.0:
                lots[res] = float(amount)
        if not lots:
            self.say("No ore in colony storage worth selling (ice reserve held back).")
            return
        multiplier = self.contracts.price_multiplier()
        proceeds, sold = self.market.sell(lots)
        proceeds *= multiplier
        colony_state.add_resources(self.colony.state, {res: -amount for res, amount in sold.items()})
        self.credits += proceeds
        self._tut["sold"] = True
        self.sim.crew_payday()
        detail = ", ".join(f"{res} {amount:,.0f} t" for res, amount in sorted(sold.items()))
        note = f" (Earth standing x{multiplier:.2f})" if abs(multiplier - 1.0) > 0.005 else ""
        self.say(f"Sold {detail} to Earth for {proceeds:,.0f} cr{note}.", seconds=8.0)

    def buy_ship_class(self, cls_key: str) -> None:
        """Commission a new ship class from the treasury."""
        if cls_key not in SHIP_CLASSES:
            self.say(f"Unknown ship class '{cls_key}'.")
            return
        spec = SHIP_CLASSES[cls_key]
        if self.credits < spec["price"]:
            self.say(
                f"A {spec['name']} costs {spec['price']:,.0f} cr; "
                f"the treasury holds {self.credits:,.0f} cr."
            )
            return
        ship, message = self.sim.buy_ship(cls_key)
        if ship is None:
            self.say(message)
            return
        self.credits -= spec["price"]
        self._tut["bought"] = True
        self.say(f"{message} Bill: {spec['price']:,.0f} cr.", seconds=8.0)

    def toggle_drill(self) -> None:
        self.sim.mining_mode = "drill" if self.sim.mining_mode == "scrape" else "scrape"
        self._tut["drilled"] = True
        flavour = (
            "core drilling: fuller holds, hull wear, incident risk"
            if self.sim.mining_mode == "drill"
            else "surface scraping: safe and steady"
        )
        self.say(f"Mining policy now {flavour}.", seconds=7.0)

    def toggle_repair(self) -> None:
        self.auto_repair = not self.auto_repair
        state = "engaged" if self.auto_repair else "suspended"
        self.say(f"Automatic hull maintenance {state}.")

    # -- save / load ----------------------------------------------------------
    def save_game(self, slot: str = "quick") -> None:
        payload = {
            "version": 2,
            "credits": self.credits,
            "auto_repair": self.auto_repair,
            "market": self.market.to_json(),
            "contracts": self.contracts.to_json(),
            "colony": self.colony.state,
            "sim": self.sim.to_json(),
        }
        path = colony_savegame.save_slot(slot, payload)
        self._tut["saved"] = True
        self.say(f"Game saved ({os.path.basename(path)}).")

    def load_game(self, slot: str = "quick") -> None:
        data = colony_savegame.load_slot(slot)
        if not data:
            self.say("No savegame found in saves/.")
            return
        self.credits = float(data.get("credits", START_CREDITS))
        self.auto_repair = bool(data.get("auto_repair", True))
        self.market = Market.from_json(data["market"])
        self.contracts = Contracts.from_json(data.get("contracts", {}), self.market)
        self.colony.state = data["colony"]
        self.sim = OpsSimulation.from_json(data["sim"])
        self.credits_history = []
        if self.scene is not None:
            # Drop meshes for ships that no longer exist in the loaded fleet.
            for name, mesh in list(self.scene.ships.items()):
                if name not in {ship.name for ship in self.sim.ships}:
                    mesh.enabled = False
                    del self.scene.ships[name]
        self.say("Savegame loaded.", seconds=6.0)

    # -- HUD feed --------------------------------------------------------------
    def _ops_hud_data(self) -> dict:
        prices = [
            (res, self.market.price(res), self.market.trend(res))
            for res in MARKET_BASE_PRICES
        ]
        target = self.hud.selected_target() if self.hud is not None else TRADE_TARGETS[0]
        return {
            "credits": self.credits,
            "prices": prices,
            "credits_spark": self._sparkline(self.credits_history),
            "mode": self.sim.mining_mode,
            "auto_repair": self.auto_repair,
            "assay": assay_lines(target, self.sim.ledger, self.sim.reserved.get(target)),
            "mined_t": float(self.sim.stats.get("ore_mined_t", 0.0)),
            "incidents": int(self.sim.stats.get("incidents", 0)),
            "hull": dict(self.sim.hull),
            "crew_line": self._crew_hud_line(),
            "weather": self.sim.weather_alert(),
            "contract_line": self._contract_hud_line(),
            "rep_line": self._reputation_hud_line(),
            "life_line": self._life_hud_line(),
            "tutorial": self.tutorial_text,
            "power_load": self.power_load,
        }

    def _crew_hud_line(self) -> str:
        morale = self.sim.fleet_morale()
        worst_name, worst_fatigue = "", 0.0
        for ship in self.sim.ships:
            _, fatigue = self.sim.crew_stats(ship.name)
            if fatigue > worst_fatigue:
                worst_name, worst_fatigue = ship.name, fatigue
        base = f"Crew morale {morale:.0f}/100"
        if worst_fatigue > 70.0:
            return f"{base} | {worst_name} crew tired ({worst_fatigue:.0f}%)"
        return base

    def _contract_hud_line(self) -> str:
        if not self.contracts.active:
            return "No Earth orders (offers every ~40 d)"
        contract = min(self.contracts.active, key=lambda c: c.deadline_day)
        pct = 100.0 * contract.progress / max(1.0, contract.tonnes)
        days_left = max(0.0, contract.deadline_day - self.market.day)
        return (f"Order: {contract.resource} {pct:.0f}% by {days_left:,.0f} d "
                f"({contract.faction})")

    def _reputation_hud_line(self) -> str:
        avg = self.contracts.average_reputation()
        mult = self.contracts.price_multiplier()
        return f"Earth standing {avg:+.0f} (prices x{mult:.2f})"

    def _life_hud_line(self) -> str:
        resources = self.colony.state.get("resources", {})
        low = LIFE_LOW_STOCK_FRACTION * 100.0

        def pct(key: str, start: float) -> float:
            return 100.0 * resources.get(key, 0.0) / max(1e-9, start)

        line = (f"Life: O2 {pct('oxygen', LIFE_START_OXYGEN):.0f}% "
                f"food {pct('food', LIFE_START_FOOD):.0f}% "
                f"water {pct('water', LIFE_START_WATER):.0f}%")
        if getattr(self, "_life_shortage_flag", False):
            return "ALERT: LIFE SUPPORT SHORTAGE - crews suffering"
        if min(pct('oxygen', LIFE_START_OXYGEN),
               pct('food', LIFE_START_FOOD),
               pct('water', LIFE_START_WATER)) < low:
            return line + "  (LOW)"
        return line

    @staticmethod
    def _sparkline(history: list[tuple[float, float]]) -> str:
        """ASCII sparkline of the treasury, oldest to newest."""
        if len(history) < 2:
            return ""
        values = [value for _, value in history]
        low, high = min(values), max(values)
        if high - low < 1e-9:
            return "-" * min(len(values), 40)
        ramps = "_.-=+*#@"
        step = max(1, len(values) // 40)
        return "".join(
            ramps[int((value - low) / (high - low) * (len(ramps) - 1))]
            for value in values[::step]
        )

    # -- colony life support ---------------------------------------------------
    def _tick_life_support(self, dt_days: float) -> None:
        """Consume and produce oxygen, food and water for the whole crew.

        The loop closes through water: an ice refinery melts stored ice, an
        electrolyser makes oxygen from water, hydroponics makes food from
        water -- all drawing on the colony's energy cell, topped up by the
        solar array. A shortage grinds on every crew's morale. This is why
        selling every tonne of ice to Earth is a real decision.
        """
        state = self.colony.state
        resources = state.setdefault("resources", {})
        crew_count = sum(len(roster) for roster in self.sim.crew.values())
        if crew_count == 0:
            return

        # The colony's solar array keeps the lights on.
        max_energy = state.get("max_energy", 30)
        resources["energy"] = min(max_energy, resources.get("energy", 0.0) + LIFE_SOLAR_ENERGY_PER_DAY * dt_days)
        energy_used = 0.0

        # Ice refinery: top the water tank up when it runs low.
        water_low = 0.5 * LIFE_START_WATER
        if resources.get("water", 0.0) < water_low and resources.get("ice", 0.0) > 0.0:
            melt = min(LIFE_ICE_MELT_RATE_PER_DAY * dt_days,
                       resources.get("ice", 0.0),
                       max(0.0, water_low - resources.get("water", 0.0)) / LIFE_ICE_TO_WATER_YIELD)
            resources["ice"] = resources.get("ice", 0.0) - melt
            resources["water"] = resources.get("water", 0.0) + melt * LIFE_ICE_TO_WATER_YIELD
            energy_used += 0.1 * melt

        need_o2 = crew_count * LIFE_OXYGEN_PER_CREW_DAY * dt_days
        need_food = crew_count * LIFE_FOOD_PER_CREW_DAY * dt_days
        need_water = crew_count * LIFE_WATER_PER_CREW_DAY * dt_days

        # Electrolysis: cover the oxygen need and refill the buffer toward its
        # starting level, so a transient stall (a fleet-wide refuel, say) can
        # actually be recovered from instead of draining the tanks forever.
        want_o2 = need_o2 + max(0.0, LIFE_START_OXYGEN - resources.get("oxygen", 0.0))
        spare_water = max(0.0, resources.get("water", 0.0) - need_water)
        budget = max(0.0, resources.get("energy", 0.0))
        made_o2 = min(want_o2,
                      spare_water / LIFE_ELECTROLYSIS_WATER_PER_O2,
                      budget / LIFE_ELECTROLYSIS_ENERGY_PER_O2)
        resources["water"] = resources.get("water", 0.0) - made_o2 * LIFE_ELECTROLYSIS_WATER_PER_O2
        resources["energy"] = resources.get("energy", 0.0) - made_o2 * LIFE_ELECTROLYSIS_ENERGY_PER_O2
        energy_used += made_o2 * LIFE_ELECTROLYSIS_ENERGY_PER_O2
        resources["oxygen"] = resources.get("oxygen", 0.0) + made_o2

        # Hydroponics: cover the calorie need and refill the food buffer.
        want_food = need_food + max(0.0, LIFE_START_FOOD - resources.get("food", 0.0))
        spare_water = max(0.0, resources.get("water", 0.0) - need_water)
        budget = max(0.0, resources.get("energy", 0.0))
        made_food = min(want_food,
                        spare_water / LIFE_HYDROPONICS_WATER_PER_FOOD,
                        budget / LIFE_HYDROPONICS_ENERGY_PER_FOOD)
        resources["water"] = resources.get("water", 0.0) - made_food * LIFE_HYDROPONICS_WATER_PER_FOOD
        resources["energy"] = resources.get("energy", 0.0) - made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
        energy_used += made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
        resources["food"] = resources.get("food", 0.0) + made_food

        # The crew breathes, eats and drinks.
        resources["oxygen"] = max(0.0, resources.get("oxygen", 0.0) - need_o2)
        resources["food"] = max(0.0, resources.get("food", 0.0) - need_food)
        resources["water"] = max(0.0, resources.get("water", 0.0) - need_water)

        # Shortages grind everyone down; the HUD and the audio alert pick up
        # the flag from _life_shortage().
        self._life_shortage_flag = (
            resources.get("oxygen", 0.0) <= 0.0 or resources.get("food", 0.0) <= 0.0
        )
        if self._life_shortage_flag:
            self.sim.apply_hardship(LIFE_SHORTAGE_MORALE_DRAIN_PER_DAY * dt_days)

        # Power load feeds the ambient hum and the HUD readout.
        reference = max(1.0, LIFE_SOLAR_ENERGY_PER_DAY * 4.0)
        load = 0.15 + 0.6 * (energy_used / dt_days) / reference
        self.power_load = min(1.0, max(0.05, load))

    def _tick_contracts(self) -> None:
        """Post fresh Earth orders and retire overdue ones."""
        offer = self.contracts.maybe_offer()
        if offer is not None and not self.headless:
            self.say(
                f"{offer.faction} orders {offer.tonnes:,.0f} t of {offer.resource} "
                f"by day {offer.deadline_day:,.0f} for {offer.reward_credits:,.0f} cr.",
                seconds=8.0,
            )
        for contract in self.contracts.expire_overdue():
            if not self.headless:
                self.say(
                    f"{contract.faction} cancelled its order for {contract.resource} "
                    f"-- standing {self.contracts.reputation[contract.faction]:+.0f}.",
                    seconds=8.0,
                )

    # -- flight-orientation checklist -------------------------------------------
    TUTORIAL_STEPS = (
        ("dispatched", "Welcome, director. Pick a target with TAB, then press ENTER to dispatch a freighter."),
        ("sold", "A run is on its way. Press S to sell stored ore on the Earth market -- watch the price flood."),
        ("drilled", "Nice. Press X to switch mining policy to core drilling: fuller holds, more wear and risk."),
        ("bought", "Press 1-4 to commission a scout, freighter, refinery or hauler once the treasury allows."),
        ("saved", "Press F5 to quick-save. F9 loads. Keep the crews fed, paid and rested -- good luck, director."),
    )

    def _tick_tutorial(self) -> None:
        if self._tut.get("done"):
            self.tutorial_text = ""
            return
        if self.sim.missions:
            self._tut["dispatched"] = True
        for key, text in self.TUTORIAL_STEPS:
            if not self._tut.get(key):
                self.tutorial_text = text
                return
        self._tut["done"] = True
        self.tutorial_text = ""

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

        # Hull maintenance for docked ships, paid from the treasury.
        if self.auto_repair:
            _, repair_cost = self.sim.repair_docked_fleet(dt_days, self.credits)
            self.credits -= repair_cost

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
            # Auto-dispatch waits for a near-full tank: launching on a sliver
            # of propellant condemns the ship to the cheapest hop forever.
            # Manual dispatch (ENTER) stays available at any propellant level.
            if ship.delta_v < 0.85 * self.sim.class_spec(ship.name)["delta_v"]:
                continue
            target = self._choose_auto_target(ship)
            if target is None:
                continue
            self.sim.dispatch(ship, target)

    def _life_ice_premium(self) -> float:
        """Extra credits-per-tonne on ice while the pantry runs low.

        Counts the tank plus the ice still in storage (melt-able), measured
        against a full round-trip horizon so the fleet stocks up *before*
        the shortage, not after it.
        """
        resources = self.colony.state.get("resources", {})
        crew_count = sum(len(roster) for roster in self.sim.crew.values())
        if crew_count == 0:
            return 0.0
        water = resources.get("water", 0.0) + LIFE_ICE_TO_WATER_YIELD * resources.get("ice", 0.0)
        days_left = water / (crew_count * (LIFE_WATER_PER_CREW_DAY
                                           + LIFE_OXYGEN_PER_CREW_DAY * LIFE_ELECTROLYSIS_WATER_PER_O2
                                           + LIFE_FOOD_PER_CREW_DAY * LIFE_HYDROPONICS_WATER_PER_FOOD))
        urgency = max(0.0, 1.0 - days_left / LIFE_ICE_HORIZON_DAYS)
        return LIFE_ICE_PREMIUM_MAX * urgency

    def _estimate_run_value(self, target_key: str, ship) -> float:
        """Estimated value of one hold at ``target_key``, life support included.

        Ice is priced at market plus the life-support premium, so a low pantry
        outbids silver and the fleet keeps the colonists fed.
        """
        spec = self.sim.class_spec(ship.name)
        payload = plan_extraction(
            target_key,
            self.sim.ledger,
            self.sim.reserved.get(target_key),
            capacity_t=ship.capacity,
            mode=self.sim.mining_mode,
            mine_bonus=spec["mine_bonus"] * self.sim.crew_yield_factor(ship.name),
            hull_pct=self.sim.mining_hull(ship),
        )
        ice_price = self.market.price("ice") + self._life_ice_premium()
        return sum(
            (ice_price if ore == "ice" else self.market.price(ore)) * tonnes
            for ore, tonnes in payload.items()
        )

    def _choose_auto_target(self, ship):
        """Most valuable run the ship can actually finish.

        Replaces the old "most expensive affordable" heuristic: value per
        delta-v reads the same vein state the miners do, so a thinned field
        naturally loses the ranking to fresher, richer rocks.
        """
        best_key = None
        best_ratio = 0.0
        for key, cost in self.sim.affordable_targets(ship):
            value = self._estimate_run_value(key, ship)
            if value <= 0.0:
                continue
            ratio = value / max(cost, 1.0)
            if ratio > best_ratio:
                best_key, best_ratio = key, ratio
        return best_key


def run_headless(sim_days: float, frames_per_day: int = 4, verbose: bool = True,
                 sell_period_days: float = 90.0) -> Game:
    """Drive the game loop with no window; used by the self-test and CI.

    The self-test exercises the whole economy: every ``sell_period_days`` the
    colony sells its ore so the treasury funds maintenance and the fleet keeps
    flying instead of decaying into a grounded state.
    """
    game = Game(headless=True)
    dt_days = 1.0 / frames_per_day
    game.sim.warp_days_per_second = 1.0  # dt already carries the time step

    # Send both freighters out so the loop has real work to do.
    game.sim.dispatch(game.sim.ships[0], "inner_belt")
    game.sim.dispatch(game.sim.ships[1], "metallic_belt")

    next_sale = sell_period_days * SIM_SECONDS_PER_DAY
    buy_index = 0
    next_buy_check = 180.0 * SIM_SECONDS_PER_DAY
    for _ in range(int(sim_days * frames_per_day)):
        game.update(dt_days)
        if sell_period_days and game.sim.time >= next_sale:
            next_sale += sell_period_days * SIM_SECONDS_PER_DAY
            game.sell_all()
        # Reinvest profits: keep a small standing fleet growing while the
        # treasury can cushion the bill, so the demo shows real progression.
        if game.sim.time >= next_buy_check:
            next_buy_check += 180.0 * SIM_SECONDS_PER_DAY
            if len(game.sim.ships) < 6:
                cls_key = BUY_MENU[buy_index % len(BUY_MENU)]
                price = SHIP_CLASSES[cls_key]["price"]
                if game.credits > price + 3000.0:
                    buy_index += 1
                    game.buy_ship_class(cls_key)

    if verbose:
        print(f"[headless] {game.frames} frames over {sim_days:,.0f} sim-days")
        for report in game.sim.fleet_report():
            hull = game.sim.hull.get(report["name"], 100.0)
            print(
                f"  {report['name']:<8}{report['status']:<9}{report['at']:<22}"
                f"{report['delta_v_left']:>8,.0f} m/s left   hull {hull:5.1f}%"
            )
        stats = game.sim.stats
        print(f"  runs completed : {stats['runs_completed']}")
        print(f"  mass delivered : {stats['mass_delivered']:,.0f} t")
        print(f"  delta-v spent  : {stats['delta_v_spent']:,.0f} m/s")
        print(f"  deliveries into colony economy: {game.deliveries_booked}")
        print(f"  colony storage : {game.colony.summary()}")
        print(f"  research points: {game.colony.state.get('research_points', 0.0):,.1f}")
        print(f"  ore mined      : {stats.get('ore_mined_t', 0.0):,.0f} t   incidents: {stats.get('incidents', 0)}")
        prices = ", ".join(f"{res} {game.market.price(res):.1f}" for res in MARKET_BASE_PRICES)
        print(f"  market day {game.market.day:,.0f} (cr/t): {prices}")
        print(f"  treasury       : {game.credits:,.0f} cr")
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
        elif key == "s":
            game.sell_all()
        elif key == "x":
            game.toggle_drill()
        elif key == "m":
            game.toggle_repair()
        elif key in ("1", "2", "3", "4"):
            game.buy_ship_class(BUY_MENU[int(key) - 1])
        elif key == "f5":
            game.save_game()
        elif key == "f9":
            game.load_game()
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
