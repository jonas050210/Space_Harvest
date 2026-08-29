"""HUD feed assembly.

Pulled out of ``src.main`` (the Game god object) so the data-shaping for the
heads-up display lives next to the UI package it feeds. Every function here is
pure read-only: it inspects the live ``Game`` and returns strings / dicts /
lists that ``OrbitalHUD.update`` consumes. No sim state, no mutation, no IO.

The feed is rebuilt every frame (headless *and* windowed), so helpers must
stay cheap. Anything that needs Lambert work (e.g. the next-windows board) is
computed and cached on ``game`` before this module is asked for the dict.
"""

from __future__ import annotations

from src.config import (  # noqa: E402
    FIRSTS,
    GAME_VERSION,
    LIFE_LOW_STOCK_FRACTION,
    LIFE_START_FOOD,
    LIFE_START_OXYGEN,
    LIFE_START_WATER,
    MARKET_BASE_PRICES,
    RIVAL_NAME,
    TECHS,
)
from src.simulation.bodies import TRADE_TARGETS  # noqa: E402
from src.campaign import body_dossier, victory_progress  # noqa: E402
from src.mining import assay_lines, body_fingerprint  # noqa: E402
from src.routes import plan_route  # noqa: E402


# -- ASCII sparkline -----------------------------------------------------------

_RAMPS = "_.-=+*#@"


def sparkline(history: list[tuple[float, float]]) -> str:
    """Render an ASCII sparkline of a 2-D history (oldest to newest)."""
    if len(history) < 2:
        return ""
    values = [value for _t, value in history]
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return "-" * min(len(values), 40)
    step = max(1, len(values) // 40)
    return "".join(
        _RAMPS[int((value - low) / (high - low) * (len(_RAMPS) - 1))]
        for value in values[::step]
    )


# -- Line helpers --------------------------------------------------------------
# Each returns a short string the HUD renders in its status ribbon. They read
# only off the game object and must not mutate anything.

def crew_hud_line(game) -> str:
    sim = game.sim
    morale = sim.fleet_morale()
    worst_name, worst_fatigue = "", 0.0
    for ship in sim.ships:
        _, fatigue = sim.crew_stats(ship.name)
        if fatigue > worst_fatigue:
            worst_name, worst_fatigue = ship.name, fatigue
    base = f"Crew morale {morale:.0f}/100"
    if worst_fatigue > 70.0:
        return f"{base} | {worst_name} crew tired ({worst_fatigue:.0f}%)"
    return base


def contract_hud_line(game) -> str:
    contracts = game.contracts
    market_day = game.market.day
    if not contracts.active:
        return "No Earth orders (offers every ~40 d)"
    contract = min(contracts.active, key=lambda c: c.deadline_day)
    pct = 100.0 * contract.progress / max(1.0, contract.tonnes)
    days_left = max(0.0, contract.deadline_day - market_day)
    return (f"Order: {contract.resource} {pct:.0f}% by {days_left:,.0f} d "
            f"({contract.faction})")


def pending_hud_line(game) -> str:
    pending = game.contracts.pending
    if not pending:
        return ""
    offer = pending[0]
    return (f"OFFER {offer.tonnes:,.0f}t {offer.resource} "
            f"{offer.reward_credits:,.0f}cr [B/V]")


def reputation_hud_line(game) -> str:
    avg = game.contracts.average_reputation()
    mult = game.contracts.price_multiplier()
    return f"Earth standing {avg:+.0f} (prices x{mult:.2f})"


def life_hud_line(game) -> str:
    resources = game.colony.state.get("resources", {})
    low = LIFE_LOW_STOCK_FRACTION * 100.0

    def pct(key: str, start: float) -> float:
        return 100.0 * resources.get(key, 0.0) / max(1e-9, start)

    line = (f"Life: O2 {pct('oxygen', LIFE_START_OXYGEN):.0f}% "
            f"food {pct('food', LIFE_START_FOOD):.0f}% "
            f"water {pct('water', LIFE_START_WATER):.0f}%")
    if getattr(game, "_life_shortage_flag", False):
        return "ALERT: LIFE SUPPORT SHORTAGE - crews suffering"
    if min(pct('oxygen', LIFE_START_OXYGEN),
           pct('food', LIFE_START_FOOD),
           pct('water', LIFE_START_WATER)) < low:
        return line + "  (LOW)"
    return line


def depot_hud_line(game) -> str:
    sim = game.sim
    if not sim.depots:
        return "No depots (R builds one: 3,500 cr)"
    parts = []
    for key, depot in sorted(sim.depots.items()):
        drones = depot.upgrades.get("drones", 0)
        parts.append(f"{sim.bodies[key].name} L{depot.level}"
                     + (f" D{drones}" if drones else "")
                     + f" {depot.fuel_ms / 1000:.1f}k/{depot.capacity / 1000:.0f}k")
    return "Depots: " + "  ".join(parts)


def depot_hint_line(game) -> str:
    if game.hud is None:
        return ""
    target = game.hud.selected_target()
    cost = game.sim.depot_upgrade_cost(target)
    verb = "Upgrade" if target in game.sim.depots else "Build"
    return f"{verb} depot at {game.sim.bodies[target].name}: {cost:,.0f} cr [R]"


def station_hint_line(game) -> str:
    if game.hud is None:
        return ""
    target = game.hud.selected_target()
    hints = []
    if target not in game.sim.depots:
        hints.append("R depot")
    if target not in game.sim.refineries:
        hints.append("E refinery")
    return "Build: " + "  ".join(hints) if hints else ""


def parts_hint_line(game) -> str:
    ship = game._best_part_ship()
    if ship is None:
        return ""
    research = game.colony.state.get("research_points", 0.0)
    for key, name, cost, _effects in TECHS:
        if key not in game.techs:
            return (f"Parts T/Y/U/I/F6scan/F7sh/F8mag  P drones  0 tanker  7-9/' modules   "
                    f"Lab [L]: {name} ({cost:.0f} RP, have {research:,.0f})")
    return "Parts T/Y/U/I/F6scan/F7sh/F8mag  P drones  0 tanker  7-9/' modules   Lab: all techs unlocked"


def swarm_hud_line(game) -> str:
    sim = game.sim
    if not sim.swarms:
        cap = sim.swarm_capacity()
        return f"Swarm ready: {cap} drones (D on GO window)" if cap >= 4 else "Swarm: build drone bays (P)"
    parts = []
    for key, swarm in sorted(sim.swarms.items()):
        name = sim.bodies[key].name if key in sim.bodies else key
        parts.append(
            f"{name} x{int(swarm['count'])} "
            f"{float(swarm['remaining_days']):.0f}d "
            f"{float(swarm.get('yield_t', 0)):.0f}t"
        )
    return "SWARM " + " | ".join(parts)


def route_hud_line(game) -> str:
    """Active multi-stop routes + planner hint for the selected target."""
    sim = game.sim
    bits = []
    for name, legs in sim.routes.items():
        if not legs:
            continue
        nxt = legs[0]
        dest = sim.bodies.get(nxt.destination)
        label = dest.name if dest else nxt.destination
        bits.append(f"{name}→{label}({nxt.purpose})")
    if game.hud is not None:
        target = game.hud.selected_target()
        idle = next((s for s in sim.ships if s.name not in sim.missions), None)
        if idle is not None:
            plan = plan_route(sim, idle, target,
                              prefer_hops=bool(game.settings.get("prefer_hops", True)))
            if plan is not None and not plan.direct:
                via = ",".join(sim.bodies[k].name for k in plan.via if k in sim.bodies)
                bits.append(f"plan via {via}" if via else "multi-stop plan")
    return "Route: " + " | ".join(bits) if bits else ""


def survey_hud_line(game) -> str:
    if game.hud is None:
        return ""
    key = game.hud.selected_target()
    sim = game.sim
    mult = sim.survey_mult(key) if hasattr(sim, "survey_mult") else 1.0
    spikes = int(getattr(sim, "isru_spikes", {}).get(key, 0))
    bits = []
    if mult > 1.01:
        bits.append(f"survey x{mult:.2f}")
    if spikes:
        bits.append(f"ISRU x{spikes}")
    return "  ".join(bits)


def route_overlay_points(game) -> list[str]:
    sim = game.sim
    if not game.settings.get("show_route_overlay", True) or game.hud is None:
        return []
    idle = next((s for s in sim.ships if s.name not in sim.missions), None)
    if idle is None:
        for _name, legs in sim.routes.items():
            keys = ["colony"]
            for leg in legs:
                if leg.destination not in keys:
                    keys.append(leg.destination)
            return keys
        return []
    plan = plan_route(
        sim, idle, game.hud.selected_target(),
        prefer_hops=bool(game.settings.get("prefer_hops", True)),
    )
    if plan is None:
        return []
    keys = ["colony"]
    for leg in plan.legs:
        if leg.destination not in keys:
            keys.append(leg.destination)
    return keys


def quest_goals(game) -> list[str]:
    """Labels of the next few un-earned milestones: the active quest log."""
    goals: list[str] = []
    progress = victory_progress(game)
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
        if progress.get("garden_goal"):
            bits.append(f"garden {progress.get('garden', 0):.0f}/{progress['garden_goal']:.0f}")
        if progress.get("needs_seedstock"):
            bits.append("seedstock" + (" OK" if progress.get("seedstock", 0) > 0 else " --"))
        goals.append(f"GOAL {progress['label']}: " + " | ".join(bits))
    for key, label, _credits, _research in FIRSTS:
        if not game.firsts.get(key):
            goals.append(label)
            if len(goals) == 3:
                break
    return goals


# -- Top-level feed dict -------------------------------------------------------

def build(game) -> dict:
    """Assemble the full extra-data dict the HUD consumes every frame."""
    market = game.market
    sim = game.sim
    prices = [
        (res, market.price(res), market.trend(res))
        for res in MARKET_BASE_PRICES
    ]
    target = game.hud.selected_target() if game.hud is not None else TRADE_TARGETS[0]
    idle_ship = game.selected_idle_ship()
    return {
        "credits": game.credits,
        "prices": prices,
        "credits_spark": sparkline(game.credits_history),
        "mode": sim.mining_mode,
        "auto_repair": game.auto_repair,
        "assay": assay_lines(target, sim.ledger, sim.reserved.get(target)),
        "mined_t": float(sim.stats.get("ore_mined_t", 0.0)),
        "incidents": int(sim.stats.get("incidents", 0)),
        "hull": dict(sim.hull),
        "crew_line": crew_hud_line(game),
        "weather": sim.weather_alert(),
        "contract_line": contract_hud_line(game),
        "pending_line": pending_hud_line(game),
        "rep_line": reputation_hud_line(game),
        "life_line": life_hud_line(game),
        "window_line": game.window_line_text,
        "window_open": game.window_is_open,
        "windows_board": game._windows_board,
        "firsts_count": (sum(1 for v in game.firsts.values() if v), len(FIRSTS)),
        "quests": quest_goals(game),
        "depot_line": depot_hud_line(game),
        "parts_hint": parts_hint_line(game),
        "station_hint": station_hint_line(game),
        "depot_hint": depot_hint_line(game),
        "tutorial": game.tutorial_text,
        "power_load": game.power_load,
        "toasts": [text for _until, text in game.toasts],
        "dossier": body_dossier(sim, target, market)
        if game.settings.get("show_dossier", True) else [],
        "pending_dispatch": game._pending_dispatch,
        "victory": victory_progress(game),
        "difficulty": game.difficulty,
        "quality": game.settings.get("quality", "medium"),
        "version": GAME_VERSION,
        "route_line": route_hud_line(game),
        "prefer_hops": bool(game.settings.get("prefer_hops", True)),
        "view_mode": game.view_mode,
        "swarm_line": swarm_hud_line(game),
        "swarm_capacity": sim.swarm_capacity(),
        "route_overlay": route_overlay_points(game),
        "survey_line": survey_hud_line(game),
        "rival_line": (RIVAL_NAME + " active") if game.settings.get("rival_enabled", True) else "",
        "selected_ship": idle_ship.name if idle_ship is not None else game.selected_ship_name,
        "price_focus": list(body_fingerprint(target)),
    }
