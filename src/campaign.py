"""Campaign rules that sit above the orbital simulation.

Difficulty, victory conditions, achievement unlocks and dispatch confirmation
live here so ``src/maths`` and ``src/simulation`` stay byte-identical to the
verified core. The game shell calls into this module; nothing here imports
Ursina.
"""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from typing import Any

from src.config import (
    ACHIEVEMENTS,
    DEFAULT_DIFFICULTY,
    DEFAULT_VICTORY,
    DIFFICULTY_MODES,
    FIRSTS,
    HULL_CRITICAL_PCT,
    HULL_MIN_PCT,
    MARKET_ABSORPTION_T,
    START_CREDITS,
    VICTORY_MODES,
)


def difficulty_spec(key: str | None) -> dict:
    return dict(DIFFICULTY_MODES.get(key or DEFAULT_DIFFICULTY,
                                     DIFFICULTY_MODES[DEFAULT_DIFFICULTY]))


def victory_spec(key: str | None) -> dict:
    return dict(VICTORY_MODES.get(key or DEFAULT_VICTORY,
                                  VICTORY_MODES[DEFAULT_VICTORY]))


def cycle_key(order: tuple[str, ...], current: str, forward: bool = True) -> str:
    if current not in order:
        return order[0]
    step = 1 if forward else -1
    return order[(order.index(current) + step) % len(order)]


def starting_credits(difficulty: str) -> float:
    spec = difficulty_spec(difficulty)
    return float(START_CREDITS) * float(spec["start_credits_mult"])


def apply_difficulty_to_market(market, difficulty: str) -> None:
    """Scale Earth absorption so Tight floods faster. Safe on a fresh Market."""
    spec = difficulty_spec(difficulty)
    mult = float(spec["market_absorption_mult"])
    market.absorption_override = {
        ore: max(1.0, tonnes * mult) for ore, tonnes in MARKET_ABSORPTION_T.items()
    }


def apply_difficulty_to_sim(sim, difficulty: str) -> None:
    """Push wear / refuel multipliers into the ops layer as generic numbers."""
    spec = difficulty_spec(difficulty)
    mults = dict(getattr(sim, "tech_mults", {}) or {})
    mults["hull_wear"] = float(spec["hull_wear_mult"])
    mults["refuel_rate"] = float(spec["refuel_rate_mult"])
    mults["life_solar"] = float(spec["life_solar_mult"])
    mults["contract_reward"] = float(spec["contract_reward_mult"])
    sim.tech_mults = mults
    # Soft-cap hull floor: ironman allows wrecks at the absolute minimum.
    if spec.get("permadeath_hull"):
        sim.hull_floor = 0.0
    else:
        sim.hull_floor = HULL_MIN_PCT


def is_ironman(difficulty: str) -> bool:
    return bool(difficulty_spec(difficulty).get("ironman"))


def check_victory(game) -> str | None:
    """Return a victory key if the active goal is met, else None."""
    mode = getattr(game, "victory_mode", DEFAULT_VICTORY)
    if mode == "endless":
        return None
    if getattr(game, "victory_achieved", None):
        return game.victory_achieved
    spec = victory_spec(mode)
    firsts_done = sum(1 for v in getattr(game, "firsts", {}).values() if v)
    tonnage = float(game.sim.stats.get("mass_delivered", 0.0))
    credits = float(getattr(game, "credits", 0.0))
    life = game.colony.state.get("logistics", {}).get("lifetime_delivered", {})
    aurellium_ok = True
    if spec.get("aurellium"):
        aurellium_ok = float(life.get("aurellium", 0.0)) > 0.0
    seed_ok = True
    if spec.get("seedstock"):
        seed_ok = float(life.get("seedstock", 0.0)) > 0.0
    garden_ok = float(game.colony.state.get("garden_score", 0.0)) >= float(spec.get("garden", 0.0) or 0.0)
    firsts_ok = firsts_done >= int(spec.get("firsts_needed", 0) or 0)
    credits_ok = credits >= float(spec.get("credits", 0.0) or 0.0)
    tonnage_ok = tonnage >= float(spec.get("tonnage", 0.0) or 0.0)
    if credits_ok and tonnage_ok and aurellium_ok and firsts_ok and seed_ok and garden_ok:
        return mode
    return None


def victory_progress(game) -> dict[str, Any]:
    """HUD-friendly progress snapshot for the active victory mode."""
    mode = getattr(game, "victory_mode", DEFAULT_VICTORY)
    spec = victory_spec(mode)
    firsts_done = sum(1 for v in getattr(game, "firsts", {}).values() if v)
    tonnage = float(game.sim.stats.get("mass_delivered", 0.0))
    credits = float(getattr(game, "credits", 0.0))
    life = game.colony.state.get("logistics", {}).get("lifetime_delivered", {})
    aurellium = float(life.get("aurellium", 0.0))
    return {
        "mode": mode,
        "label": spec["label"],
        "credits": credits,
        "credits_goal": float(spec.get("credits", 0.0) or 0.0),
        "tonnage": tonnage,
        "tonnage_goal": float(spec.get("tonnage", 0.0) or 0.0),
        "firsts": firsts_done,
        "firsts_goal": int(spec.get("firsts_needed", 0) or 0),
        "aurellium": aurellium,
        "needs_aurellium": bool(spec.get("aurellium")),
        "garden": float(game.colony.state.get("garden_score", 0.0)),
        "garden_goal": float(spec.get("garden", 0.0) or 0.0),
        "needs_seedstock": bool(spec.get("seedstock")),
        "seedstock": float(life.get("seedstock", 0.0)),
        "achieved": bool(getattr(game, "victory_achieved", None)),
    }


def dispatch_preview(sim, ship, target_key: str) -> dict[str, Any]:
    """Numbers the confirm sheet shows before ENTER commits a dispatch."""
    body = sim.bodies.get(target_key)
    name = body.name if body is not None else target_key
    plan = None
    try:
        plan = sim.plan_round_trip("colony", target_key)
    except Exception:
        plan = None
    window = sim.launch_window("colony", target_key)
    dv_budget = float(sim.effective_delta_v(ship.name))
    hull = float(sim.hull.get(ship.name, 100.0))
    morale, fatigue = sim.crew_stats(ship.name)
    outbound = arrive = total = 0.0
    wait_days = float("inf")
    tof_days = 0.0
    if plan is not None:
        # plan is (outbound_window, return_window) or similar -- be defensive
        try:
            out_w, ret_w = plan[0], plan[1]
            outbound = float(sim.delta_v_km_s(out_w.total_delta_v) * 1000.0)
            arrive = float(sim.delta_v_km_s(ret_w.total_delta_v) * 1000.0)
            total = outbound + arrive
            wait_days = max(0.0, (out_w.departure_time - sim.time) / (2.0 * 3.1415926535 / 365.25))
            # Prefer the canonical day conversion if the sim exposes it later.
        except Exception:
            pass
    if window is not None:
        try:
            from src.config import SIM_SECONDS_PER_DAY
            wait_days = max(0.0, (window.departure_time - sim.time) / SIM_SECONDS_PER_DAY)
            tof_days = float(window.tof / SIM_SECONDS_PER_DAY)
            outbound = float(sim.delta_v_km_s(window.dv_depart) * 1000.0)
            arrive = float(sim.delta_v_km_s(window.dv_arrive) * 1000.0)
            total = float(sim.delta_v_km_s(window.total_delta_v) * 1000.0) * 2.0
        except Exception:
            pass
    affordable = total <= dv_budget * 1.05 if total > 0 else True
    blocked = []
    if hull < HULL_CRITICAL_PCT:
        blocked.append(f"hull critical ({hull:.0f}%)")
    if fatigue >= 90.0:
        blocked.append(f"crew exhausted ({fatigue:.0f}%)")
    if not affordable and total > 0:
        blocked.append(f"delta-v short ({total:,.0f} needed / {dv_budget:,.0f} have)")
    return {
        "ship": ship.name,
        "target": target_key,
        "target_name": name,
        "wait_days": wait_days,
        "tof_days": tof_days,
        "outbound_ms": outbound,
        "return_ms": arrive,
        "total_ms": total,
        "budget_ms": dv_budget,
        "hull": hull,
        "morale": morale,
        "fatigue": fatigue,
        "affordable": affordable,
        "blocked": blocked,
        "ok": not blocked,
    }


class AchievementTracker:
    """Latch Firsts + secret achievements and mirror them for Steam."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join("saves", "achievements_progress.json")
        self.unlocked: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.unlocked = {str(k): float(v) for k, v in data.get("unlocked", {}).items()}
        except Exception:
            self.unlocked = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        payload = {
            "version": 1,
            "updated": time.time(),
            "unlocked": dict(self.unlocked),
            "catalog": list(ACHIEVEMENTS),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self.path)

    def unlock(self, key: str) -> bool:
        if key in self.unlocked:
            return False
        if key not in ACHIEVEMENTS and not key.startswith("first_") and not key.startswith("secret_"):
            return False
        self.unlocked[key] = time.time()
        self.save()
        return True

    def sync_firsts(self, firsts: dict[str, bool]) -> list[str]:
        """Mirror fired Firsts into the achievement file. Returns newly unlocked."""
        fresh = []
        for key, fired in firsts.items():
            if fired and self.unlock(key):
                fresh.append(key)
        return fresh

    def to_json(self) -> dict:
        return {"unlocked": dict(self.unlocked)}


def body_dossier(sim, target_key: str, market=None) -> list[str]:
    """Short multi-line dossier for the selected body (HUD card)."""
    body = sim.bodies.get(target_key)
    if body is None:
        return [f"Unknown body: {target_key}"]
    lines = [f"{body.name}", body.description or ""]
    try:
        from src.mining import assay_lines
        assay = assay_lines(target_key, sim.ledger, sim.reserved.get(target_key))
        if assay:
            lines.append(f"Assay  {assay}")
    except Exception:
        pass
    depot = sim.depots.get(target_key)
    if depot is not None:
        lines.append(
            f"Depot L{depot.level}  fuel {depot.fuel_ms/1000:.1f}k m/s"
            + (f"  drones x{depot.upgrades.get('drones', 0)}" if depot.upgrades.get("drones") else "")
        )
    else:
        lines.append("No depot (R to build)")
    if target_key in sim.refineries:
        lines.append("Refinery online")
    window = sim.launch_window("colony", target_key)
    if window is not None:
        try:
            from src.config import SIM_SECONDS_PER_DAY
            wait = max(0.0, (window.departure_time - sim.time) / SIM_SECONDS_PER_DAY)
            lines.append(f"Next window in {wait:,.0f} d")
        except Exception:
            pass
    if market is not None:
        try:
            top = sorted(
                ((ore, market.price(ore)) for ore in getattr(body, "resources", ()) or ()),
                key=lambda item: -item[1],
            )[:3]
            if top:
                lines.append("Spot  " + "  ".join(f"{o} {p:.0f}" for o, p in top))
        except Exception:
            pass
    return [line for line in lines if line]


def year_report(game) -> list[str]:
    """Pause-menu / end-of-year summary lines."""
    from src.config import SIM_SECONDS_PER_DAY

    stats = game.sim.stats
    firsts = sum(1 for v in game.firsts.values() if v)
    return [
        f"Mission day        {game.sim.time / SIM_SECONDS_PER_DAY:,.0f}",
        f"Runs completed     {stats.get('runs_completed', 0)}",
        f"Mass delivered     {stats.get('mass_delivered', 0.0):,.0f} t",
        f"Ore mined          {stats.get('ore_mined_t', 0.0):,.0f} t",
        f"Incidents          {stats.get('incidents', 0)}",
        f"Treasury           {game.credits:,.0f} cr",
        f"Firsts             {firsts}/{len(FIRSTS)}",
        f"Fleet size         {len(game.sim.ships)}",
        f"Depots / refineries {len(game.sim.depots)} / {len(game.sim.refineries)}",
        f"Difficulty         {difficulty_spec(getattr(game, 'difficulty', DEFAULT_DIFFICULTY))['label']}",
        f"Victory mode       {victory_spec(getattr(game, 'victory_mode', DEFAULT_VICTORY))['label']}",
        f"Garden score       {float(game.colony.state.get('garden_score', 0.0)):.1f}",
    ]


def campaign_blob(game) -> dict:
    """Slice of campaign state to persist inside the savegame."""
    return {
        "difficulty": getattr(game, "difficulty", DEFAULT_DIFFICULTY),
        "victory": getattr(game, "victory_mode", DEFAULT_VICTORY),
        "victory_achieved": getattr(game, "victory_achieved", None),
        "achievements": deepcopy(getattr(getattr(game, "achievements", None), "unlocked", {})),
        "clean_run_streak": int(getattr(game, "clean_run_streak", 0)),
        "ironman_days": float(getattr(game, "ironman_days", 0.0)),
    }


def restore_campaign_blob(game, data: dict | None) -> None:
    data = data or {}
    game.difficulty = data.get("difficulty", DEFAULT_DIFFICULTY)
    game.victory_mode = data.get("victory", DEFAULT_VICTORY)
    game.victory_achieved = data.get("victory_achieved")
    game.clean_run_streak = int(data.get("clean_run_streak", 0))
    game.ironman_days = float(data.get("ironman_days", 0.0))
    if hasattr(game, "achievements") and isinstance(data.get("achievements"), dict):
        game.achievements.unlocked.update(
            {str(k): float(v) for k, v in data["achievements"].items()}
        )
