#!/usr/bin/env python3
"""Space Harvest -- orbital farming on real launch windows.

Entry point. Runs the patched-conic simulation from ``src.simulation`` inside a
Ursina window and books every freighter delivery into the colony economy
(``src/game/logistics.py``), so storage, research and life support respond to
what the harvest brings home.

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
    LIFE_WATER_RECYCLE_FRACTION,
    CREW_BOTANIST_SAVING_CAP,
    CREW_BOTANIST_WATER_SAVING,
    CREW_HIRE_COST,
    DEFAULT_DIFFICULTY,
    DEFAULT_SETTINGS,
    DEFAULT_VICTORY,
    DEPOT_BUILD_COST,
    DIFFICULTY_MODES,
    FIRSTS,
    GAME_NAME,
    GAME_TAGLINE,
    GAME_VERSION,
    HULL_CRITICAL_PCT,
    PARTS_CATALOG,
    QUALITY_ORDER,
    QUALITY_PRESETS,
    SAVE_SLOTS,
    TECHS,
    MARKET_BASE_PRICES,
    REDISPATCH_SCAN_DAYS,
    SHIP_CLASSES,
    SHIP_REFUEL_ENERGY_PER_MS,
    START_CREDITS,
    TIME_WARP_STEPS,
    VICTORY_MODES,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from src.simulation.bodies import TRADE_TARGETS  # noqa: E402
from src.config import SIM_SECONDS_PER_DAY  # noqa: E402
from src.campaign import (  # noqa: E402
    AchievementTracker,
    apply_difficulty_to_market,
    apply_difficulty_to_sim,
    body_dossier,
    campaign_blob,
    check_victory,
    dispatch_preview,
    is_ironman,
    restore_campaign_blob,
    starting_credits,
    victory_progress,
    year_report,
)
from src.display import apply_window_settings, volume_from_settings  # noqa: E402
from src.mining import assay_lines, plan_extraction  # noqa: E402
from src.market import Contracts, Market  # noqa: E402
from src.operations import OpsSimulation  # noqa: E402
from src.simulation.orbital_sim import OrbitalSimulation  # noqa: E402
from src.steam_bridge import SteamClient, cloud_root  # noqa: E402
from src.routes import plan_route, route_preview_lines  # noqa: E402

try:  # windowed-only import; headless keeps working without Ursina
    from ursina import Vec3, lerp  # noqa: E402
except Exception:  # pragma: no cover
    Vec3 = None  # type: ignore[assignment]
    lerp = None  # type: ignore[assignment]

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
        # resource -> market day of the most recent delivery, so Earth orders
        # what the fleet actually trades these days.
        self._recent_deliveries: dict[str, float] = {}
        # One-shot flags the flight-orientation checklist watches.
        self.tutorial_text = ""
        self._tut = {"dispatched": False, "sold": False, "drilled": False,
                     "bought": False, "saved": False, "done": False}
        # Screen state: title -> play; ESC toggles pause (windowed only).
        self.screen = "play" if headless else "title"
        self.paused = False
        # Persistent player settings (graphics, audio, campaign defaults).
        self.settings = self._load_settings() if not headless else dict(DEFAULT_SETTINGS)
        self.toasts: list[tuple[float, str]] = []
        # KSP-style one-shot milestones (see config.FIRSTS).
        self.firsts: dict[str, bool] = {}
        # Science unlocks (see config.TECHS).
        self.techs: set = set()
        self._parts_discount = 0.0
        self._firsts_frame = 0
        self._window_fired_day: dict[str, float] = {}
        self._window_dep_day: dict[str, float] = {}
        self._camera_goal = None
        self._windows_board: list[tuple[str, float, bool]] = []
        self._board_frame = 0
        # Jump-to-event: (label, absolute sim time) the warp is racing toward.
        self._jump_target: tuple[str, float] | None = None
        self._jump_warp_restore: float | None = None
        self.muted = False
        # Alert edges, so tones play once per incident instead of every frame.
        self._alert_edges = {"flare": False, "hull": False, "shortage": False}
        # Procedural audio (windowed only): hum + alert tones, synthesised at
        # startup. None in headless mode.
        self.audio: dict | None = None
        self.scene = None
        self.hud = None
        self.follow_target: str | None = None
        self.frames = 0
        self.deliveries_booked = 0
        self._message = ""
        self._message_until = 0.0
        # Campaign layer (difficulty / victory / achievements / Steam).
        self.difficulty = self.settings.get("difficulty", DEFAULT_DIFFICULTY)
        self.victory_mode = self.settings.get("victory", DEFAULT_VICTORY)
        self.victory_achieved: str | None = None
        self.clean_run_streak = 0
        self.ironman_days = 0.0
        self._pending_dispatch: dict | None = None
        self.achievements = AchievementTracker(
            path=os.path.join(cloud_root(), "achievements_progress.json"))
        self.steam = SteamClient()
        self._apply_campaign_rules()

    # -- messaging -----------------------------------------------------------
    def say(self, text: str, seconds: float = 6.0) -> None:
        self._message = text
        self._message_until = time.time() + seconds
        self.toasts.append((time.time() + seconds, text))
        if len(self.toasts) > 4:
            del self.toasts[: len(self.toasts) - 4]
        print(f"[game] {text}")

    def _current_message(self) -> str:
        return self._message if time.time() < self._message_until else ""

    # -- scene ---------------------------------------------------------------
    def build_scene(self, ursina_scene) -> None:
        """Create the 3-D network view and the HUD. Windowed mode only."""
        from src.entities.orbital_scene import OrbitalScene
        from src.ui.orbital_hud import OrbitalHUD

        self.scene = OrbitalScene(parent=ursina_scene)
        self.hud = OrbitalHUD(self.sim.trade_targets)
        self.set_camera_preset("network")

    def set_camera_preset(self, preset: str) -> None:
        from ursina import Vec3, camera

        presets = {"network": Vec3(0, 46, -52), "close": Vec3(0, 12, -18), "top": Vec3(0, 78, -1)}
        if preset in presets:
            self._camera_goal = presets[preset]
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
        from ursina import camera

        glide = 0.10 if self.settings.get("glide", True) else 1.0
        if self.follow_target is None or self.scene is None:
            # Glide back to the network anchor when no ship is followed.
            if self._camera_goal is not None:
                camera.position = lerp(camera.position, self._camera_goal, 0.045 if self.settings.get("glide", True) else 1.0)
                camera.look_at(Vec3(0, 0, 0))
            return
        ship = self.scene.ships.get(self.follow_target)
        if ship is None:
            return
        offset = camera.position - ship.position
        distance = offset.length()
        if distance > 26.0 or distance < 6.0:
            offset = offset.normalized() * 14.0 if distance > 1e-3 else (0, 6, -14)
        # Exponential smoothing: the chase settles instead of snapping.
        goal = ship.position + offset
        camera.position = lerp(camera.position, goal, glide)
        camera.look_at(ship.position)

    def pick_body(self, entity) -> None:
        """Select the clicked body as transfer target (windowed)."""
        if self.hud is None:
            return
        node = entity
        while node is not None:
            key = getattr(node, "body_key", None)
            if key is not None:
                if self.hud.set_target(key):
                    self._play_alert("click")
                    self.say(f"Target: {self.sim.bodies[key].name}.")
                return
            node = getattr(node, "parent", None)

    # -- actions -------------------------------------------------------------
    def dispatch_selected(self, confirm: bool = False) -> None:
        """Dispatch an idle ship. With confirm_dispatch on, first ENTER previews."""
        if self.hud is None and not self.headless:
            return
        target = (self.hud.selected_target() if self.hud is not None
                  else TRADE_TARGETS[0])
        idle = next((ship for ship in self.sim.ships if ship.name not in self.sim.missions), None)
        if idle is None:
            self.say("Every freighter is already flying a mission.")
            self._pending_dispatch = None
            return
        want_confirm = bool(self.settings.get("confirm_dispatch", True)) and not self.headless
        if want_confirm and not confirm:
            preview = dispatch_preview(self.sim, idle, target)
            prefer = bool(self.settings.get("prefer_hops", True))
            plan = plan_route(self.sim, idle, target, prefer_hops=prefer)
            route_lines = route_preview_lines(plan, self.sim.bodies) if plan else []
            self._pending_dispatch = {
                "ship": idle.name, "target": target, "preview": preview,
                "route": route_lines, "plan_direct": bool(plan.direct) if plan else True,
            }
            if preview["blocked"] and (plan is None or plan.direct):
                self.say("HOLD: " + "; ".join(preview["blocked"]), seconds=7.0)
            elif plan is not None and not plan.direct:
                self.say(
                    f"CONFIRM multi-stop {idle.name}: {plan.summary_line()}  "
                    f"(ENTER again / ESC cancel)",
                    seconds=10.0,
                )
            else:
                self.say(
                    f"CONFIRM {idle.name} -> {preview['target_name']}: "
                    f"wait {preview['wait_days']:,.0f}d  "
                    f"dv {preview['total_ms']:,.0f}/{preview['budget_ms']:,.0f} m/s  "
                    f"(ENTER again / ESC cancel)",
                    seconds=9.0,
                )
            return
        # Honour a pending confirm only for the same ship/target.
        if self._pending_dispatch is not None:
            if (self._pending_dispatch.get("ship") != idle.name
                    or self._pending_dispatch.get("target") != target):
                # Selection changed -- treat as a fresh preview next time.
                self._pending_dispatch = None
                return self.dispatch_selected(confirm=False)
        self._pending_dispatch = None
        prefer = bool(self.settings.get("prefer_hops", True))
        self.sim.standing_orders["prefer_hops"] = prefer
        # Multi-stop when direct will not fit; else normal dispatch.
        plan = plan_route(self.sim, idle, target, prefer_hops=prefer)
        if plan is not None and not plan.direct and plan.hop_count > 0:
            ok, message = self.sim.dispatch_route(idle, target)
            if ok:
                self.sim.stats["multihop_runs"] = int(self.sim.stats.get("multihop_runs", 0)) + 1
        else:
            ok, message = self.sim.dispatch(idle, target)
        self.say(message, seconds=8.0)

    def cancel_pending_dispatch(self) -> None:
        if self._pending_dispatch is not None:
            self._pending_dispatch = None
            self.say("Dispatch cancelled.")

    def _apply_campaign_rules(self) -> None:
        """Push difficulty numbers into market + sim without naming them there."""
        apply_difficulty_to_market(self.market, self.difficulty)
        apply_difficulty_to_sim(self.sim, self.difficulty)
        # Re-apply tech multipliers on top so difficulty does not wipe science.
        self._apply_techs()

    def _apply_techs_preserve_difficulty(self) -> None:
        self._apply_techs()
        apply_difficulty_to_sim(self.sim, self.difficulty)

    # -- main loop -----------------------------------------------------------
    def update(self, dt_days: float) -> None:
        """Advance one frame by ``dt_days`` of simulation time.

        Callers pass seconds times the warp rate, so windowed and headless
        modes run the identical code path. Title and pause states skip the
        simulation but keep the scene alive.
        """
        if self.screen == "title":
            self._tick_title()
            return
        if self.paused:
            if self.hud is not None:
                self.hud.update(self.sim, self.colony.summary(), "PAUSED - ESC to resume",
                                extra=self._ops_hud_data())
            return
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
        self._tick_audio()
        self._tick_jump()
        self._tick_window_moments()
        self._tick_firsts()
        self._tick_victory()
        if is_ironman(self.difficulty):
            self.ironman_days += dt_days
            if self.ironman_days >= 365.0:
                if self.achievements.unlock("secret_ironman_year"):
                    self.steam.unlock("secret_ironman_year")
                    self.say("ACHIEVEMENT: Survived a full year on Ironman.", seconds=8.0)
        if self.steam is not None:
            try:
                self.steam.tick(0.0)  # real-time playtime tracked in windowed loop
            except Exception:
                pass

        if self.scene is not None:
            self.scene.update(self.sim)
            if self.screen == "title":
                self._drift_camera()
            else:
                self.update_camera()
        if self.hud is not None:
            self._update_windows_board()
            self.hud.update(self.sim, self.colony.summary(), self._current_message(),
                            extra=self._ops_hud_data())
            if self.scene is not None:
                self.scene.set_reticle(self.hud.selected_target(), self.sim)
            if self.sim.log:
                self.hud.ticker.text = f"tail  {self.sim.log[-1].text[:120]}"[:130]

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
            for ore in delivery.cargo:
                self._recent_deliveries[ore] = self.market.day
            for contract in self.contracts.register_delivery(delivery.cargo):
                reward = self.contracts.complete(contract)
                reward *= float(self.sim.tech_mults.get("contract_reward", 1.0))
                self.credits += reward
                self._play_alert("contract")
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


    # -- settings & campaign lifecycle --------------------------------------------
    SETTINGS_SLOT = "_settings"

    def _load_settings(self) -> dict:
        data = colony_savegame.load_slot(self.SETTINGS_SLOT)
        settings = dict(DEFAULT_SETTINGS)
        if isinstance(data, dict):
            for key in settings:
                if key in data:
                    settings[key] = data[key]
        # Clamp quality to a known preset (older saves may say "high" only).
        if settings.get("quality") not in QUALITY_ORDER:
            settings["quality"] = "medium"
        return settings

    def save_settings(self) -> None:
        colony_savegame.save_slot(self.SETTINGS_SLOT, dict(self.settings))

    def apply_settings(self) -> None:
        """Push the settings into scene, mixer, window and camera; persist them."""
        if self.scene is not None:
            preset = QUALITY_PRESETS.get(self.settings.get("quality", "medium"),
                                         QUALITY_PRESETS["medium"])
            self.scene.apply_quality(**preset)
        # Display (resolution / fullscreen / vsync / FOV) -- windowed only.
        if not self.headless:
            try:
                apply_window_settings(self.settings)
            except Exception:
                pass
        vol = volume_from_settings(self.settings)
        if self.audio is not None:
            hum = self.audio.get("hum")
            if hum is not None:
                try:
                    hum.volume = 0.0 if self.settings.get("muted") else max(0.05, vol * 0.4)
                except Exception:
                    pass
            for key, sound in self.audio.items():
                if key == "hum" or sound is None:
                    continue
                try:
                    sound.volume = vol
                except Exception:
                    pass
        self.muted = bool(self.settings.get("muted", False))
        # Campaign defaults chosen in settings stick for the next NEW GAME.
        if "difficulty" in self.settings:
            pass  # applied in new_campaign from settings
        self.save_settings()

    def new_campaign(self, difficulty: str | None = None, victory: str | None = None) -> None:
        """A fresh director, same solar system."""
        self.difficulty = difficulty or self.settings.get("difficulty", DEFAULT_DIFFICULTY)
        self.victory_mode = victory or self.settings.get("victory", DEFAULT_VICTORY)
        self.victory_achieved = None
        self.clean_run_streak = 0
        self.ironman_days = 0.0
        self._pending_dispatch = None
        self.sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
        self.colony = Colony()
        self.market = Market()
        self.contracts = Contracts(self.market)
        self.credits = starting_credits(self.difficulty)
        self.credits_history = []
        self.toasts = []
        self.firsts = {}
        self.techs = set()
        self._apply_campaign_rules()
        self.deliveries_booked = 0
        self.screen = "play"
        self.paused = False
        self.settings["difficulty"] = self.difficulty
        self.settings["victory"] = self.victory_mode
        self.save_settings()
        if self.scene is not None:
            for mesh in self.scene.ships.values():
                mesh.enabled = False
                mesh.clear_trail()
            self.scene.ships.clear()
            self.scene.ensure_bodies(self.sim)
            self.apply_settings()
        diff_label = DIFFICULTY_MODES.get(self.difficulty, {}).get("label", self.difficulty)
        vic_label = VICTORY_MODES.get(self.victory_mode, {}).get("label", self.victory_mode)
        self.say(
            f"New harvest -- {diff_label} / {vic_label}. The belt is yours, director.",
            seconds=8.0,
        )

    def to_title(self) -> None:
        self.screen = "title"
        self.paused = False
        self.save_game("quick")  # a courtesy autosave on the way out

    # -- title screen -----------------------------------------------------------
    def _tick_title(self) -> None:
        self.frames += 1
        if self.scene is not None:
            self.scene.update(self.sim)
            self._drift_camera()
        if self.hud is not None:
            self.hud.update(self.sim, self.colony.summary(),
                            "press ENTER to launch", extra=None)

    def _drift_camera(self) -> None:
        """Slow cinematic orbit on the title screen."""
        import math as _math

        from ursina import camera

        angle = self.frames * 0.0025
        radius = 58.0
        camera.position = Vec3(radius * _math.cos(angle), 26.0, radius * _math.sin(angle))
        camera.look_at(Vec3(0, 0, 0))

    def start_game(self) -> None:
        if self.screen != "title":
            return
        self.screen = "play"
        self.say("Space Harvest online. TAB a field, wait for the window, harvest the belt.",
                 seconds=9.0)

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
            "version": 3,
            "credits": self.credits,
            "auto_repair": self.auto_repair,
            "market": self.market.to_json(),
            "contracts": self.contracts.to_json(),
            "firsts": dict(self.firsts),
            "techs": sorted(self.techs),
            "colony": self.colony.state,
            "sim": self.sim.to_json(),
            "campaign": campaign_blob(self),
            "game_version": GAME_VERSION,
        }
        path = colony_savegame.save_slot(slot, payload)
        self._tut["saved"] = True
        self.say(f"Game saved ({os.path.basename(path)}).")

    def load_game(self, slot: str = "quick") -> None:
        if is_ironman(self.difficulty) and slot != "quick" and self.screen == "play":
            # Ironman still allows loading the single quick slot on boot, but
            # refuses mid-run "rewind" loads from the pause menu path.
            pass
        data = colony_savegame.load_slot(slot)
        if not data:
            self.say("No savegame found in saves/.")
            return
        self.credits = float(data.get("credits", START_CREDITS))
        self.auto_repair = bool(data.get("auto_repair", True))
        self.market = Market.from_json(data["market"])
        self.contracts = Contracts.from_json(data.get("contracts", {}), self.market)
        self.firsts = {k: bool(v) for k, v in data.get("firsts", {}).items()}
        self.techs = set(data.get("techs", []))
        self.colony.state = data["colony"]
        self.sim = OpsSimulation.from_json(data["sim"])
        restore_campaign_blob(self, data.get("campaign"))
        self._apply_campaign_rules()
        self.credits_history = []
        self._pending_dispatch = None
        if self.scene is not None:
            # Drop meshes for ships that no longer exist in the loaded fleet.
            for name, mesh in list(self.scene.ships.items()):
                if name not in {ship.name for ship in self.sim.ships}:
                    mesh.enabled = False
                    del self.scene.ships[name]
        self.say("Savegame loaded.", seconds=6.0)

    def try_load(self, slot: str = "quick") -> None:
        """Load with Ironman guard: no mid-run F9 on Ironman campaigns."""
        if is_ironman(self.difficulty) and self.screen == "play" and not self.paused:
            self.say("Ironman: no mid-flight loads. Pause and Quit to Title to abandon.")
            return
        if is_ironman(getattr(self, "difficulty", DEFAULT_DIFFICULTY)):
            # Allow load only from title (continue) -- pause menu blocks F9.
            if self.screen == "play" and self.paused:
                self.say("Ironman: loading disabled. Survive or quit to title.")
                return
        self.load_game(slot)

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
            "pending_line": self._pending_hud_line(),
            "rep_line": self._reputation_hud_line(),
            "life_line": self._life_hud_line(),
            "window_line": self.window_line_text,
            "window_open": self.window_is_open,
            "windows_board": self._windows_board,
            "firsts_count": (sum(1 for v in self.firsts.values() if v), len(FIRSTS)),
            "quests": self._quest_goals(),
            "depot_line": self._depot_hud_line(),
            "parts_hint": self._parts_hint_line(),
            "station_hint": self._station_hint_line(),
            "depot_hint": self._depot_hint_line(),
            "tutorial": self.tutorial_text,
            "power_load": self.power_load,
            "toasts": [text for _until, text in self.toasts],
            "dossier": body_dossier(self.sim, target, self.market)
            if self.settings.get("show_dossier", True) else [],
            "pending_dispatch": self._pending_dispatch,
            "victory": victory_progress(self),
            "difficulty": self.difficulty,
            "quality": self.settings.get("quality", "medium"),
            "version": GAME_VERSION,
            "route_line": self._route_hud_line(),
            "prefer_hops": bool(self.settings.get("prefer_hops", True)),
        }

    # -- "Firsts": one-shot milestones ------------------------------------------
    def _first_conditions(self) -> dict:
        """Read-only predicates for every milestone in config.FIRSTS."""
        sim = self.sim
        captures = sim.stats.get("captures_by_body", {})
        return {
            "first_dispatch": bool(sim.missions) or sim.stats["runs_completed"] >= 1,
            "first_capture_belt": captures.get("inner_belt", 0) >= 1,
            "first_capture_metallic": captures.get("metallic_belt", 0) >= 1,
            "first_capture_deep": captures.get("deep_belt", 0) >= 1,
            "first_capture_derelict": captures.get("derelict_zone", 0) >= 1,
            "first_capture_aurelia": captures.get("gas_giant_orbit", 0) >= 1,
            "first_capture_comet": captures.get("comet_vigil", 0) >= 1,
            "first_depot": len(sim.depots) >= 1,
            "first_refinery": len(sim.refineries) >= 1,
            "first_drones": any(d.upgrades.get("drones", 0) >= 1 for d in sim.depots.values()),
            "full_return_1": sim.stats.get("full_returns", 0) >= 1,
            "full_return_10": sim.stats.get("full_returns", 0) >= 10,
            "mass_2500": sim.stats["mass_delivered"] >= 2500.0,
            "mass_10000": sim.stats["mass_delivered"] >= 10000.0,
            "fleet_5": len(sim.ships) >= 5,
            "rich_25k": self.credits >= 25_000.0,
            "rich_100k": self.credits >= 100_000.0,
            "thorite_1": self.colony.state.get("logistics", {}).get("lifetime_delivered", {}).get("thorite", 0.0) > 0.0,
            "aurellium_1": self.colony.state.get("logistics", {}).get("lifetime_delivered", {}).get("aurellium", 0.0) > 0.0,
            "first_capture_trojan": captures.get("trojan_field", 0) >= 1,
            "first_capture_cinder": captures.get("cinder_moon", 0) >= 1,
            "first_capture_outer": captures.get("outer_reach", 0) >= 1,
            "first_multihop": int(self.sim.stats.get("multihop_runs", 0)) >= 1,
            "helium3_1": self.colony.state.get("logistics", {}).get("lifetime_delivered", {}).get("helium3", 0.0) > 0.0,
            "obsidian_1": self.colony.state.get("logistics", {}).get("lifetime_delivered", {}).get("obsidian", 0.0) > 0.0,
        }

    def _tick_firsts(self) -> None:
        self._firsts_frame += 1
        if self._firsts_frame % 30 != 1:  # a few times a second at most
            return
        conditions = self._first_conditions()
        for key, label, credits, research in FIRSTS:
            if self.firsts.get(key):
                continue
            if conditions.get(key):
                self.firsts[key] = True
                if credits:
                    self.credits += credits
                self.colony.state["research_points"] = float(
                    self.colony.state.get("research_points", 0.0)) + research
                self._play_alert("contract")
                self.say(f"MILESTONE: {label}  (+{credits:,.0f} cr, +{research:.0f} RP)",
                         seconds=9.0)
                if self.achievements.unlock(key):
                    self.steam.unlock(key)
        # Secret: zero-incident professional streak.
        incidents = int(self.sim.stats.get("incidents", 0))
        runs = int(self.sim.stats.get("runs_completed", 0))
        if runs >= 10 and incidents == 0:
            if self.achievements.unlock("secret_zero_incident_streak"):
                self.steam.unlock("secret_zero_incident_streak")
                self.say("ACHIEVEMENT: Ten clean runs -- no incidents.", seconds=8.0)

    def _tick_victory(self) -> None:
        if self.victory_achieved:
            return
        key = check_victory(self)
        if key is None:
            return
        self.victory_achieved = key
        label = VICTORY_MODES.get(key, {}).get("label", key)
        self._play_alert("contract")
        self.say(f"VICTORY -- {label}. The charter is sealed.", seconds=12.0)
        if self.achievements.unlock("secret_charter_clear"):
            self.steam.unlock("secret_charter_clear")

    def _quest_goals(self) -> list[str]:
        """Labels of the next few un-earned milestones: the active quest log."""
        goals = []
        progress = victory_progress(self)
        if progress["mode"] != "endless" and not progress["achieved"]:
            bits = []
            if progress["credits_goal"]:
                bits.append(f"cr {progress['credits']:,.0f}/{progress['credits_goal']:,.0f}")
            if progress["tonnage_goal"]:
                bits.append(f"t {progress['tonnage']:,.0f}/{progress['tonnage_goal']:,.0f}")
            if progress["firsts_goal"]:
                bits.append(f"firsts {progress['firsts']}/{progress['firsts_goal']}")
            if progress["needs_aurellium"]:
                bits.append("aurellium" + (" OK" if progress["aurellium"] > 0 else " --"))
            goals.append(f"GOAL {progress['label']}: " + " | ".join(bits))
        for key, label, _credits, _research in FIRSTS:
            if not self.firsts.get(key):
                goals.append(label)
                if len(goals) == 3:
                    break
        return goals

    def _update_windows_board(self) -> None:
        """Soonest-next launch windows across the whole network.

        Throttled: a full-network solve is only expensive the first time
        (the window cache holds afterwards).
        """
        self._board_frame += 1
        if self._board_frame % 45 != 1 and self._windows_board:
            return
        rows: list[tuple[str, float, bool]] = []
        for key in self.sim.trade_targets:
            window = self.sim.launch_window("colony", key)
            name = self.sim.bodies[key].name
            if window is None:
                rows.append((name, float("inf"), False))
                continue
            days = (window.departure_time - self.sim.time) / SIM_SECONDS_PER_DAY
            rows.append((name, days, days <= 1.0))
        rows.sort(key=lambda row: row[1])
        self._windows_board = rows

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

    def _route_hud_line(self) -> str:
        """Active multi-stop routes + planner hint for the selected target."""
        bits = []
        for name, legs in self.sim.routes.items():
            if not legs:
                continue
            nxt = legs[0]
            dest = self.sim.bodies.get(nxt.destination)
            label = dest.name if dest else nxt.destination
            bits.append(f"{name}→{label}({nxt.purpose})")
        if self.hud is not None:
            target = self.hud.selected_target()
            idle = next((s for s in self.sim.ships if s.name not in self.sim.missions), None)
            if idle is not None:
                plan = plan_route(self.sim, idle, target,
                                  prefer_hops=bool(self.settings.get("prefer_hops", True)))
                if plan is not None and not plan.direct:
                    via = ",".join(self.sim.bodies[k].name for k in plan.via if k in self.sim.bodies)
                    bits.append(f"plan via {via}" if via else "multi-stop plan")
        return "Route: " + " | ".join(bits) if bits else ""

    def toggle_prefer_hops(self) -> None:
        self.settings["prefer_hops"] = not bool(self.settings.get("prefer_hops", True))
        self.sim.standing_orders["prefer_hops"] = self.settings["prefer_hops"]
        self.save_settings()
        state = "ON" if self.settings["prefer_hops"] else "OFF"
        self.say(f"Multi-stop refuel hops {state}.", seconds=5.0)

    def _station_hint_line(self) -> str:
        if self.hud is None:
            return ""
        target = self.hud.selected_target()
        hints = []
        if target not in self.sim.depots:
            hints.append("R depot")
        if target not in self.sim.refineries:
            hints.append("E refinery")
        return "Build: " + "  ".join(hints) if hints else ""

    def _parts_hint_line(self) -> str:
        ship = self._best_part_ship()
        if ship is None:
            return ""
        research = self.colony.state.get("research_points", 0.0)
        for key, name, cost, _effects in TECHS:
            if key not in self.techs:
                return (f"Parts [T]ank [Y]drill [U]arters [I]nav [P]drones   "
                        f"Lab [L]: {name} ({cost:.0f} RP, have {research:,.0f})")
        return "Parts [T]ank [Y]drill [U]arters [I]nav [P]drones   Lab: all techs unlocked"

    def _depot_hud_line(self) -> str:
        if not self.sim.depots:
            return "No depots (R builds one: 3,500 cr)"
        parts = []
        for key, depot in sorted(self.sim.depots.items()):
            drones = depot.upgrades.get("drones", 0)
            parts.append(f"{self.sim.bodies[key].name} L{depot.level}"
                         + (f" D{drones}" if drones else "")
                         + f" {depot.fuel_ms / 1000:.1f}k/{depot.capacity / 1000:.0f}k")
        return "Depots: " + "  ".join(parts)

    def _depot_hint_line(self) -> str:
        if self.hud is None:
            return ""
        target = self.hud.selected_target()
        cost = self.sim.depot_upgrade_cost(target)
        verb = "Upgrade" if target in self.sim.depots else "Build"
        return f"{verb} depot at {self.sim.bodies[target].name}: {cost:,.0f} cr [R]"

    def _pending_hud_line(self) -> str:
        if not self.contracts.pending:
            return ""
        offer = self.contracts.pending[0]
        return (f"OFFER {offer.tonnes:,.0f}t {offer.resource} "
                f"{offer.reward_credits:,.0f}cr [B/V]")

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

        # The colony's solar array keeps the lights on (difficulty can dim it).
        max_energy = state.get("max_energy", 30)
        solar = LIFE_SOLAR_ENERGY_PER_DAY * float(self.sim.tech_mults.get("life_solar", 1.0))
        resources["energy"] = min(max_energy, resources.get("energy", 0.0) + solar * dt_days)
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
        water_per_food = LIFE_HYDROPONICS_WATER_PER_FOOD * self.sim.botanist_water_factor()
        made_food = min(want_food,
                        spare_water / water_per_food,
                        budget / LIFE_HYDROPONICS_ENERGY_PER_FOOD)
        resources["water"] = resources.get("water", 0.0) - made_food * water_per_food
        resources["energy"] = resources.get("energy", 0.0) - made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
        energy_used += made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
        resources["food"] = resources.get("food", 0.0) + made_food

        # The crew breathes, eats and drinks; the recyclers claw most of the
        # water back into the tank.
        water_used = need_water + made_o2 * LIFE_ELECTROLYSIS_WATER_PER_O2 \
            + made_food * LIFE_HYDROPONICS_WATER_PER_FOOD
        resources["oxygen"] = max(0.0, resources.get("oxygen", 0.0) - need_o2)
        resources["food"] = max(0.0, resources.get("food", 0.0) - need_food)
        resources["water"] = max(0.0, resources.get("water", 0.0) - need_water)
        resources["water"] = resources.get("water", 0.0) + water_used * LIFE_WATER_RECYCLE_FRACTION

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
        """Post offers, honour decisions, retire overdue and stale paper."""
        # Sorted: set iteration order is hash-randomised between processes,
        # and Earth's choice must not depend on it.
        recent = sorted(ore for ore, day in self._recent_deliveries.items()
                        if self.market.day - day < 1200.0)
        if not recent:
            recent = sorted(self.colony.state.get("logistics", {}).get("lifetime_delivered", {}))
        offer = self.contracts.maybe_offer(recent)
        if offer is not None and not self.headless:
            self.say(
                f"OFFER from {offer.faction}: {offer.tonnes:,.0f} t of {offer.resource} "
                f"by day {offer.deadline_day:,.0f} for {offer.reward_credits:,.0f} cr. "
                "B to accept, V to decline.",
                seconds=9.0,
            )
        # The autopilot accepts orders it plausibly can fill.
        if self.headless:
            for pending in list(self.contracts.pending):
                if pending.resource in recent and len(self.contracts.active) < 2:
                    self.contracts.accept(pending.id)
        for withdrawn in self.contracts.expire_pending():
            if not self.headless:
                self.say(f"{withdrawn.faction} withdrew its offer for {withdrawn.resource}.")
        for contract in self.contracts.expire_overdue():
            if not self.headless:
                self.say(
                    f"{contract.faction} cancelled its order for {contract.resource} "
                    f"-- standing {self.contracts.reputation[contract.faction]:+.0f}.",
                    seconds=8.0,
                )

    def _best_part_ship(self):
        """Docked-at-colony ship with the fewest upgrades: spread the love."""
        candidates = [s for s in self.sim.ships
                      if s.name not in self.sim.missions and s.origin == "colony"]
        if not candidates:
            return None
        return min(candidates, key=lambda s: sum(self.sim.upgrades.get(s.name, {}).values()))

    def buy_part(self, part_key: str) -> None:
        """Buy an upgrade part from the Earth parts market."""
        info = PARTS_CATALOG.get(part_key)
        if info is None or part_key == "drones":
            self.say("Unknown part.")
            return
        ship = self._best_part_ship()
        if ship is None:
            self.say("No ship is docked at the colony for a refit.")
            return
        owned = sum(self.sim.upgrades.get(s.name, {}).get(part_key, 0)
                    for s in self.sim.ships)
        price = self.market.part_price(part_key, owned) * (1.0 - self._parts_discount)
        if self.credits < price:
            self.say(f"{info['name']} costs {price:,.0f} cr; treasury {self.credits:,.0f} cr.")
            return
        aurellium_t = float(info.get("aurellium_t", 0.0))
        if aurellium_t > 0.0:
            resources = self.colony.state.get("resources", {})
            if resources.get("aurellium", 0.0) < aurellium_t:
                self.say(f"The {info['name']} needs {aurellium_t:.0f} t aurellium -- "
                         "only Comet Vigil carries it.")
                return
        ok, message = self.sim.install_part(ship.name, part_key)
        if not ok:
            self.say(message)
            return
        self.credits -= price
        if aurellium_t > 0.0:
            colony_state.add_resources(self.colony.state, {"aurellium": -aurellium_t})
        self._play_alert("build")
        note = f" and {aurellium_t:.0f} t aurellium" if aurellium_t else ""
        self.say(f"{message} Bill {price:,.0f} cr{note}.", seconds=7.0)

    # -- science -------------------------------------------------------------------
    def _apply_techs(self) -> None:
        """Translate owned techs into generic sim multipliers + a price break.

        Difficulty multipliers (hull_wear, refuel_rate, ...) are re-applied
        afterwards so science never wipes the campaign rules.
        """
        mults: dict[str, float] = {}
        discount = 0.0
        for key in self.techs:
            for effect in TECHS:
                if effect[0] != key:
                    continue
                for name, value in effect[3].items():
                    if name == "parts_discount":
                        discount = max(discount, value)
                    else:
                        mults[name] = mults.get(name, 1.0) * value
        # Preserve difficulty-only keys if already set.
        for key in ("hull_wear", "refuel_rate", "life_solar", "contract_reward"):
            if key in getattr(self.sim, "tech_mults", {}):
                mults.setdefault(key, self.sim.tech_mults[key])
        self.sim.tech_mults = mults
        self._parts_discount = discount
        apply_difficulty_to_sim(self.sim, getattr(self, "difficulty", DEFAULT_DIFFICULTY))

    def buy_tech(self) -> None:
        """Commission the cheapest affordable unowned technology."""
        research = self.colony.state.get("research_points", 0.0)
        for key, name, cost, _effects in TECHS:
            if key in self.techs:
                continue
            if research < cost:
                self.say(f"{name} needs {cost:.0f} RP; the colony holds {research:,.0f} RP.")
                return
            self.techs.add(key)
            self.colony.state["research_points"] = research - cost
            self._apply_techs()
            self._play_alert("contract")
            self.say(f"RESEARCH COMPLETE: {name}.", seconds=8.0)
            return
        if not self.headless:
            self.say("Every technology is already unlocked.")

    def buy_drone_bay(self) -> None:
        """Install a drone bay at the selected target's depot."""
        target = self.hud.selected_target() if self.hud is not None else "deep_belt"
        depot = self.sim.depots.get(target)
        if depot is None:
            self.say("Build a depot there first (R).")
            return
        owned = depot.upgrades.get("drones", 0)
        price = self.market.part_price("drones", owned)
        if self.credits < price:
            self.say(f"A drone bay costs {price:,.0f} cr; treasury {self.credits:,.0f} cr.")
            return
        ok, message = self.sim.install_depot_part(target, "drones")
        if not ok:
            self.say(message)
            return
        self.credits -= price
        self._play_alert("build")
        self.say(f"{message} Bill {price:,.0f} cr.", seconds=7.0)

    def build_refinery_selected(self) -> None:
        """Build a smelting station at the selected body."""
        target = self.hud.selected_target() if self.hud is not None else "metallic_belt"
        cost = self.sim.refinery_upgrade_cost(target)
        if self.credits < cost:
            self.say(f"A refinery costs {cost:,.0f} cr; the treasury holds {self.credits:,.0f} cr.")
            return
        ok, message = self.sim.build_refinery(target)
        if not ok:
            self.say(message)
            return
        self.credits -= cost
        self._play_alert("build")
        self.say(f"{message} Bill: {cost:,.0f} cr. Waiting runs arrive refined.", seconds=8.0)

    def build_depot_selected(self) -> None:
        """Build (or upgrade) a refuel depot at the selected body.

        Headless mode has no selection, so it defaults to the deep belt --
        the depot site that unlocks the far network.
        """
        target = self.hud.selected_target() if self.hud is not None else "deep_belt"
        cost = self.sim.depot_upgrade_cost(target)
        if self.credits < cost:
            self.say(f"A depot at {self.sim.bodies[target].name} costs {cost:,.0f} cr; "
                     f"the treasury holds {self.credits:,.0f} cr.")
            return
        ok, message = self.sim.build_depot(target)
        if not ok:
            self.say(message)
            return
        self.credits -= cost
        self._play_alert("build")
        self.say(f"{message} Bill: {cost:,.0f} cr.", seconds=8.0)

    def accept_contract(self) -> None:
        """Accept the oldest posted offer."""
        if not self.contracts.pending:
            self.say("No offers on the desk.")
            return
        offer = self.contracts.pending[0]
        accepted = self.contracts.accept(offer.id)
        if accepted is None:
            self.say("The order book is full; finish or fail a standing order first.")
            return
        self.say(
            f"Accepted: {accepted.tonnes:,.0f} t {accepted.resource} for "
            f"{accepted.faction} -- {accepted.reward_credits:,.0f} cr on delivery.",
            seconds=8.0,
        )

    def decline_contract(self) -> None:
        offer = self.contracts.decline(self.contracts.pending[0].id) if self.contracts.pending else None
        self.say("Offer declined." if offer else "No offers on the desk.")

    # -- hiring ------------------------------------------------------------------
    def hire(self, role: str) -> None:
        cost = CREW_HIRE_COST.get(role)
        if cost is None:
            self.say(f"Nobody trains '{role}' here.")
            return
        if self.credits < cost:
            self.say(f"A {role} costs {cost:,.0f} cr signing bonus; treasury holds {self.credits:,.0f} cr.")
            return
        if role == "botanist":
            ok, message = self.sim.hire("botanist")
        else:
            ship = min(self.sim.ships, key=lambda s: len(self.sim.crew.get(s.name, [])))
            ok, message = self.sim.hire(role, ship.name)
        if not ok:
            self.say(message)
            return
        self.credits -= cost
        self.say(f"{message} Signing bonus {cost:,.0f} cr.")

    def fire_worst_morale(self) -> None:
        candidates = [(m, ship.name) for ship in self.sim.ships
                      for m in self.sim.crew.get(ship.name, [])]
        if not candidates:
            self.say("No one to dismiss.")
            return
        member, ship_name = min(candidates, key=lambda item: item[0].morale)
        ok, message = self.sim.fire(ship_name, member)
        self.say(message)

    # -- jump-to-event -------------------------------------------------------------
    def upcoming_events(self) -> list[tuple[str, float]]:
        """Timed things worth racing the warp toward."""
        events: list[tuple[str, float]] = []
        if self.hud is not None:
            window = self.sim.launch_window("colony", self.hud.selected_target())
            if window is not None and window.departure_time > self.sim.time:
                events.append((f"window to {self.sim.bodies[self.hud.selected_target()].name}",
                               window.departure_time))
        for ship in self.sim.ships:
            mission = self.sim.missions.get(ship.name)
            if mission is not None:
                events.append((f"{ship.name} {mission.leg.value} completes",
                               self.sim._event_time(mission)))
        if self.sim.flare_state == "quiet":
            events.append(("flare warning", self.sim.time + max(0.0, self.sim._flare_timer)))
        for contract in self.contracts.active:
            events.append((f"{contract.resource} order due", contract.deadline_day * SIM_SECONDS_PER_DAY))
        for contract in self.contracts.pending:
            events.append((f"{contract.resource} offer expires",
                           (contract.deadline_day - 30.0) * SIM_SECONDS_PER_DAY))
        return [e for e in events if e[1] > self.sim.time + SIM_SECONDS_PER_DAY]

    def cycle_jump(self) -> None:
        """Pick the next upcoming event and race the warp toward it."""
        events = sorted(self.upcoming_events(), key=lambda e: e[1])
        if not events:
            self.say("Nothing worth jumping to right now.")
            return
        label, when = events[0]
        if self._jump_target is not None:
            index = next((i for i, e in enumerate(events) if abs(e[1] - self._jump_target[1]) < 1e-6), -1)
            label, when = events[(index + 1) % len(events)]
        self._jump_target = (label, when)
        if self._jump_warp_restore is None:
            self._jump_warp_restore = self.sim.warp_days_per_second
        self.sim.warp_days_per_second = max(TIME_WARP_STEPS)
        self.say(f"Jumping to {label} in {(when - self.sim.time) / SIM_SECONDS_PER_DAY:,.0f} days.",
                 seconds=6.0)

    window_line_text = ""
    window_is_open = False

    def _tick_window_moments(self) -> None:
        """Announce the launch-window GO moment for the selected target.

        The window cache holds a departure opportunity while it is still in
        the future and transparently re-solves once it passes, so the only
        way to see the instant a window *arrives* is to watch for sim time
        crossing the departure we recorded on an earlier tick.
        """
        self.window_is_open = False
        if self.hud is None:
            return
        target = self.hud.selected_target()
        window = self.sim.launch_window("colony", target)
        if window is None:
            self.window_line_text = ""
            return
        wait_days = max(0.0, (window.departure_time - self.sim.time) / SIM_SECONDS_PER_DAY)
        crossed = self._window_dep_day.get(target)
        if crossed is not None and self.sim.time >= crossed > self.sim.time - 6.0 * SIM_SECONDS_PER_DAY:
            # The recorded opportunity is departing right about now: GO.
            self.window_is_open = True
            last = self._window_fired_day.get(target, -1.0e9)
            if self.sim.time - last > 40.0 * SIM_SECONDS_PER_DAY:
                self._window_fired_day[target] = self.sim.time
                self._play_alert("window")
                self.say(f"LAUNCH WINDOW OPEN -- {self.sim.bodies[target].name} -- press ENTER",
                         seconds=8.0)
        self._window_dep_day[target] = window.departure_time
        if self.window_is_open:
            self.window_line_text = "LAUNCH WINDOW OPEN  --  ENTER to dispatch"
        else:
            self.window_line_text = f"Window to {self.sim.bodies[target].name} in {wait_days:,.0f} d"

    def _tick_jump(self) -> None:
        if self._jump_target is None:
            return
        label, when = self._jump_target
        if self.sim.time >= when:
            self._jump_target = None
            if self._jump_warp_restore is not None:
                self.sim.warp_days_per_second = self._jump_warp_restore
                self._jump_warp_restore = None
            if not self.headless:
                self.say(f"Arrived at: {label}.", seconds=5.0)

    # -- flight-orientation checklist -------------------------------------------
    TUTORIAL_STEPS = (
        ("dispatched",
         "Welcome to Space Harvest. TAB picks a field (asteroid). Wait for GO, then ENTER to send a freighter."),
        ("sold",
         "Harvest is flying home. Press S to sell ore on Earth -- dump one market and its price floods."),
        ("drilled",
         "Press X for core drilling: richer holds, more wear and risk. Surface scrape stays safer."),
        ("bought",
         "Press 1-4 to commission a scout, freighter, refinery-ship or hauler when the treasury allows."),
        ("saved",
         "F5 quick-saves, F9 loads (blocked on Ironman). Keep crews fed and the pantry iced -- good luck."),
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

    # -- procedural audio ------------------------------------------------------
    def _tick_audio(self) -> None:
        """Follow the power load with the hum; play alerts on rising edges.

        The hum ducks under any recent alert so the tone reads clearly, and
        the whole mixer mutes with N for quiet play.
        """
        if not self.audio:
            return
        hum = self.audio.get("hum")
        if hum is not None:
            try:
                if self.muted:
                    hum.volume = 0.0
                else:
                    ducking = time.time() < getattr(self, "_duck_until", 0.0)
                    hum.volume = (0.05 if ducking else 0.15) + 0.55 * self.power_load * (0.3 if ducking else 1.0)
                    hum.pitch = 0.85 + 0.45 * self.power_load
            except Exception:
                pass

        hull_critical = any(pct < HULL_CRITICAL_PCT for pct in self.sim.hull.values())
        edges = {
            "flare": self.sim.flare_state in ("warning", "flare"),
            "hull": hull_critical,
            "shortage": bool(getattr(self, "_life_shortage_flag", False)),
        }
        for kind, active in edges.items():
            if active and not self._alert_edges.get(kind):
                self._play_alert(kind)
            self._alert_edges[kind] = active

    def _play_alert(self, kind: str) -> None:
        if not self.audio or self.muted:
            return
        sound = self.audio.get(kind)
        if sound is None:
            return
        try:
            sound.play()
            self._duck_until = time.time() + 1.2
        except Exception:
            pass

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        self.say("Audio muted." if self.muted else "Audio on.")

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
            prefer = bool(self.settings.get("prefer_hops", True))
            plan = plan_route(self.sim, ship, target, prefer_hops=prefer)
            if plan is not None and not plan.direct and plan.hop_count > 0:
                ok, _ = self.sim.dispatch_route(ship, target)
                if ok:
                    self.sim.stats["multihop_runs"] = int(self.sim.stats.get("multihop_runs", 0)) + 1
            else:
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
        # Quadratic: comfortable pantries barely move the dispatcher; a real
        # shortage outbids the metals market. Linear urgency made every ship
        # mine ice forever and nobody haul metal.
        return LIFE_ICE_PREMIUM_MAX * urgency * urgency

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
        # A deep-belt depot unlocks the far network for the whole fleet.
        depot_cost = game.sim.depot_upgrade_cost("deep_belt")
        depot_level = game.sim.depots["deep_belt"].level if "deep_belt" in game.sim.depots else 0
        if depot_level < 2 and game.credits > depot_cost + 6000.0:
            game.build_depot_selected()
        # A refinery turns runs into refined stock: free margin every visit.
        if "inner_belt" not in game.sim.refineries:
            refinery_cost = game.sim.refinery_upgrade_cost("inner_belt")
            if game.credits > refinery_cost + 9000.0:
                game.sim.build_refinery("inner_belt")
        # Science: spend research as it accumulates so the self-test
        # exercises the tech path end to end (multipliers, discounts).
        if (game.colony.state.get("research_points", 0.0) > 80.0
                and len(game.techs) < len(TECHS)):
            game.buy_tech()

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


def _setup_audio(game: "Game") -> None:
    """Synthesise the ambient hum and alert tones; never fatal if audio fails."""
    try:
        from ursina import Audio

        from src.utils.procedural import make_alert_wav, make_hum_wav

        directory = os.path.join("logs", "audio")
        os.makedirs(directory, exist_ok=True)
        audio = {"hum": Audio(make_hum_wav(os.path.join(directory, "hum.wav")),
                              loop=True, autoplay=True)}
        for kind in ("flare", "hull", "shortage", "contract", "build", "window"):
            audio[kind] = Audio(make_alert_wav(kind, os.path.join(directory, f"{kind}.wav")),
                                autoplay=False)
        game.audio = audio
        print("[audio] procedural hum and alert tones ready")
    except Exception as exc:  # no audio device / no numpy wave support
        game.audio = None
        print(f"[audio] disabled ({exc})")


def run_windowed() -> None:
    from ursina import Ursina, camera, color, mouse, window
    from ursina import scene as ursina_scene
    from ursina import application

    # Ursina is a singleton and ``run`` is an *instance* method, so the
    # application object has to be kept; ``application.run()`` does not exist.
    from src.display import parse_resolution
    res = parse_resolution(str(DEFAULT_SETTINGS.get("resolution", "1440x900")))
    app = Ursina(title=f"{WINDOW_TITLE}  v{GAME_VERSION}", size=res, borderless=False)
    window.color = color.black

    game = Game(headless=False)
    game.build_scene(ursina_scene)
    _setup_audio(game)
    from src.game import savegame as colony_savegame
    from src.ui.orbital_hud import MenuOverlay

    menus = MenuOverlay(continue_available=bool(colony_savegame.list_saves()))
    menus.on_settings_changed = lambda s: (game.settings.update(s), game.apply_settings())
    game.apply_settings()
    menus.show_main(continue_available=bool(colony_savegame.list_saves()))
    camera.orthographic = False
    camera.fov = float(game.settings.get("fov", 55))

    def _latest_slot() -> str | None:
        files = colony_savegame.list_saves()
        for name in files:
            if name not in ("_settings.json", "achievements_progress.json", "steam_stats.json"):
                return name[:-5] if name.endswith(".json") else name
        return None

    def _menu_action(action: str) -> None:
        if action == "new_game":
            # NEW GAME pulls difficulty/victory from the settings the player set.
            game.new_campaign(
                difficulty=game.settings.get("difficulty"),
                victory=game.settings.get("victory"),
            )
            menus.hide()
        elif action == "continue":
            game.load_game("quick")
            game.screen = "play"
            menus.hide()
        elif action == "load":
            slot = _latest_slot()
            if slot:
                game.load_game(slot)
                game.screen = "play"
                menus.hide()
            else:
                game.say("No saves yet.")
        elif action == "settings":
            menus.show_settings(game.settings)
        elif action == "howto":
            menus.show_howto(0)
        elif action == "report":
            menus.show_report(year_report(game))
        elif action == "save":
            game.save_game("quick")
            menus.show_pause()
        elif action == "save_slot1":
            game.save_game("slot1"); menus.show_pause()
        elif action == "save_slot2":
            game.save_game("slot2"); menus.show_pause()
        elif action == "save_slot3":
            game.save_game("slot3"); menus.show_pause()
        elif action == "resume":
            game.paused = False
            menus.hide()
        elif action == "quit_to_title":
            game.to_title()
            menus.show_main(continue_available=True)
        elif action == "back":
            if game.paused:
                menus.show_pause()
            else:
                menus.show_main(continue_available=bool(colony_savegame.list_saves()))
        elif action == "quit":
            try:
                game.steam.shutdown()
            except Exception:
                pass
            application.quit()

    _last_real = time.time()

    def update():
        nonlocal _last_real
        now = time.time()
        real_dt = max(0.0, min(0.1, now - _last_real))
        _last_real = now
        try:
            game.steam.tick(real_dt)
        except Exception:
            pass
        if game.screen == "title" or game.paused:
            game.update(0.0)
            return
        dt_days = real_dt * game.sim.warp_days_per_second
        game.update(dt_days)

    def input(key):
        # --- menu states ----------------------------------------------------
        if game.screen == "title" or game.paused:
            if key == "escape" and game.screen == "title" and menus.screen == "main":
                try:
                    game.steam.shutdown()
                except Exception:
                    pass
                application.quit()
                return
            action = menus.handle(key)
            if action:
                _menu_action(action)
            if game.screen == "play" and not game.paused and menus.screen in ("main", "pause"):
                menus.hide()
            return
        # --- live play --------------------------------------------------------
        if key == "escape":
            if game._pending_dispatch is not None:
                game.cancel_pending_dispatch()
                return
            game.paused = True
            menus.show_pause()
            return
        if key == "q":
            try:
                game.steam.shutdown()
            except Exception:
                pass
            application.quit()
            return
        if key == "left mouse down":
            game.pick_body(mouse.hovered_entity)
        elif key == "tab" and game.hud is not None:
            game.hud.cycle_target(1)
            game.say(f"Target: {game.hud.selected_target()}")
        elif key == "enter":
            if game._pending_dispatch is not None:
                game.dispatch_selected(confirm=True)
            else:
                game.dispatch_selected(confirm=False)
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
        elif key == "j":
            game.cycle_jump()
        elif key == "b":
            game.accept_contract()
        elif key == "v":
            game.decline_contract()
        elif key == "g":
            game.hire("miner")
        elif key == "h":
            game.fire_worst_morale()
        elif key == "z":
            game.hire("botanist")
        elif key == "r":
            game.build_depot_selected()
        elif key == "e":
            game.build_refinery_selected()
        elif key == "t":
            game.buy_part("tank")
        elif key == "y":
            game.buy_part("drill")
        elif key == "u":
            game.buy_part("quarters")
        elif key == "p":
            game.buy_drone_bay()
        elif key == "i":
            game.buy_part("navsuite")
        elif key == "l":
            game.buy_tech()
        elif key == "k":
            order = QUALITY_ORDER
            current = game.settings.get("quality", "medium")
            idx = order.index(current) if current in order else 0
            game.settings["quality"] = order[(idx + 1) % len(order)]
            game.apply_settings()
            game.say(f"Quality: {game.settings['quality']}.")
        elif key == "n":
            game.settings["muted"] = not game.settings.get("muted", False)
            game.apply_settings()
            game.say("Audio muted." if game.muted else "Audio on.")
        elif key == "f5":
            game.save_game()
        elif key == "f9":
            game.try_load()
        elif key == "f1":
            menus.show_report(year_report(game))
            game.paused = True

    # Ursina discovers the loop and input handler through this module's globals.
    import sys as _sys
    this_module = _sys.modules[__name__]
    this_module.update = update
    this_module.input = input
    globals()["update"] = update
    globals()["input"] = input

    app.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Space Harvest — orbital farming on real launch windows")
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
