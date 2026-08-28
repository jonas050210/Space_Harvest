"""Multi-stop delivery planner (KSP-style refuel hops).

Sits above the orbital core: every leg is a real Lambert window from
``OpsSimulation.launch_window`` / ``plan_round_trip``. The planner only
decides *which sequence of bodies* a freighter should visit so a deep harvest
that cannot be flown direct still fits the tank -- by docking at player-built
depots along the way.

Nothing here edits ``src/maths`` or ``src/simulation``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import (
    ROUTE_COST_SLACK,
    ROUTE_MAX_HOPS,
    ROUTE_PREFER_DEPOT_HOPS,
    SIM_SECONDS_PER_DAY,
)


@dataclass
class RouteLeg:
    """One hop of a planned multi-stop run."""

    origin: str
    destination: str
    purpose: str = "transfer"  # transfer | harvest | refuel | home
    outbound_ms: float = 0.0
    return_ms: float = 0.0
    wait_days: float = 0.0
    tof_days: float = 0.0
    needs_depot: bool = False


@dataclass
class RoutePlan:
    """A full itinerary the ops layer can fly leg-by-leg."""

    destination: str
    legs: list[RouteLeg] = field(default_factory=list)
    total_ms: float = 0.0
    hop_count: int = 0
    via: list[str] = field(default_factory=list)
    direct: bool = True
    reason: str = ""

    def summary_line(self) -> str:
        if self.direct and not self.via:
            return f"Direct  {self.total_ms:,.0f} m/s"
        path = " → ".join(["colony", *self.via, self.destination, "colony"])
        return f"Via {'/'.join(self.via) or '—'}  {self.total_ms:,.0f} m/s  ({self.hop_count} hops)  {path}"


def _leg_cost(sim, origin: str, dest: str) -> tuple[float, float, float, float] | None:
    """Return (outbound_ms, return_ms, wait_days, tof_days) or None."""
    try:
        outbound, inbound = sim.plan_round_trip(origin, dest, max_age=None)
    except Exception:
        return None
    if outbound is None:
        return None
    out_ms = float(sim.delta_v_km_s(outbound.total_delta_v) * 1000.0)
    back_ms = 0.0
    if inbound is not None:
        back_ms = float(sim.delta_v_km_s(inbound.total_delta_v) * 1000.0)
    wait = max(0.0, (outbound.departure_time - sim.time) / SIM_SECONDS_PER_DAY)
    tof = float(outbound.tof / SIM_SECONDS_PER_DAY)
    return out_ms, back_ms, wait, tof


def _one_way(sim, origin: str, dest: str) -> tuple[float, float, float] | None:
    window = sim.launch_window(origin, dest)
    if window is None:
        return None
    ms = float(sim.delta_v_km_s(window.total_delta_v) * 1000.0)
    wait = max(0.0, (window.departure_time - sim.time) / SIM_SECONDS_PER_DAY)
    tof = float(window.tof / SIM_SECONDS_PER_DAY)
    return ms, wait, tof


def plan_direct(sim, destination: str) -> RoutePlan | None:
    costs = _leg_cost(sim, "colony", destination)
    if costs is None:
        return None
    out_ms, back_ms, wait, tof = costs
    total = out_ms + back_ms
    return RoutePlan(
        destination=destination,
        legs=[
            RouteLeg("colony", destination, "harvest", out_ms, 0.0, wait, tof),
            RouteLeg(destination, "colony", "home", back_ms, 0.0, 0.0, 0.0),
        ],
        total_ms=total,
        hop_count=0,
        via=[],
        direct=True,
        reason="direct round trip",
    )


def plan_via_depot(sim, destination: str, depot_key: str) -> RoutePlan | None:
    """colony → depot (refuel) → destination (harvest) → depot → colony.

    Propellant accounting treats each hop as a fresh tank fill at the depot,
    so the ship only needs enough delta-v for the *hardest single hop*, not
    the sum -- matching how ISRU barns work in play.
    """
    hop1 = _one_way(sim, "colony", depot_key)
    hop2 = _one_way(sim, depot_key, destination)
    hop3 = _one_way(sim, destination, depot_key)
    hop4 = _one_way(sim, depot_key, "colony")
    if None in (hop1, hop2, hop3, hop4):
        return None
    legs = [
        RouteLeg("colony", depot_key, "refuel", hop1[0], 0.0, hop1[1], hop1[2], needs_depot=True),
        RouteLeg(depot_key, destination, "harvest", hop2[0], 0.0, hop2[1], hop2[2]),
        RouteLeg(destination, depot_key, "refuel", hop3[0], 0.0, hop3[1], hop3[2], needs_depot=True),
        RouteLeg(depot_key, "colony", "home", hop4[0], 0.0, hop4[1], hop4[2]),
    ]
    # Tank requirement = max hop (refuel at each depot stop); billed total is sum.
    peak = max(leg.outbound_ms for leg in legs)
    total = sum(leg.outbound_ms for leg in legs)
    return RoutePlan(
        destination=destination,
        legs=legs,
        total_ms=total,
        hop_count=1,
        via=[depot_key],
        direct=False,
        reason=f"refuel hop via {depot_key} (peak tank {peak:,.0f} m/s)",
    )


def plan_via_two_depots(sim, destination: str, first: str, second: str) -> RoutePlan | None:
    """colony → A → B → destination → B → A → colony (two-barn deep run)."""
    sequence = [
        ("colony", first, "refuel"),
        (first, second, "refuel"),
        (second, destination, "harvest"),
        (destination, second, "refuel"),
        (second, first, "refuel"),
        (first, "colony", "home"),
    ]
    legs: list[RouteLeg] = []
    for origin, dest, purpose in sequence:
        hop = _one_way(sim, origin, dest)
        if hop is None:
            return None
        legs.append(RouteLeg(origin, dest, purpose, hop[0], 0.0, hop[1], hop[2],
                             needs_depot=purpose == "refuel" and dest != "colony"))
    peak = max(leg.outbound_ms for leg in legs)
    total = sum(leg.outbound_ms for leg in legs)
    return RoutePlan(
        destination=destination,
        legs=legs,
        total_ms=total,
        hop_count=2,
        via=[first, second],
        direct=False,
        reason=f"two-hop via {first}+{second} (peak {peak:,.0f} m/s)",
    )


def available_depots(sim) -> list[str]:
    return sorted(getattr(sim, "depots", {}).keys())


def plan_route(
    sim,
    ship,
    destination: str,
    *,
    prefer_hops: bool = ROUTE_PREFER_DEPOT_HOPS,
    max_hops: int = ROUTE_MAX_HOPS,
) -> RoutePlan | None:
    """Pick the best route the ship can actually fly right now.

    Preference order:
      1. Direct round trip if the tank covers it.
      2. Single-depot hop if a barn exists and peak hop fits the tank.
      3. Two-depot hop for Outer Reach-class runs.
    """
    budget = float(getattr(sim, "effective_delta_v", lambda n: ship.delta_v)(ship.name)
                   if hasattr(sim, "effective_delta_v") else ship.delta_v)
    # Drop tanks already folded into effective_delta_v by ops.
    candidates: list[RoutePlan] = []

    direct = plan_direct(sim, destination)
    if direct is not None:
        candidates.append(direct)

    depots = available_depots(sim)
    if max_hops >= 1 and depots:
        for depot in depots:
            if depot == destination:
                continue
            plan = plan_via_depot(sim, destination, depot)
            if plan is not None:
                candidates.append(plan)
    if max_hops >= 2 and len(depots) >= 2:
        for i, a in enumerate(depots):
            for b in depots[i + 1:]:
                if destination in (a, b):
                    continue
                plan = plan_via_two_depots(sim, destination, a, b)
                if plan is not None:
                    candidates.append(plan)
                plan = plan_via_two_depots(sim, destination, b, a)
                if plan is not None:
                    candidates.append(plan)

    if not candidates:
        return None

    def peak_required(plan: RoutePlan) -> float:
        if plan.direct:
            return plan.total_ms
        return max((leg.outbound_ms for leg in plan.legs), default=plan.total_ms)

    affordable = [p for p in candidates if peak_required(p) <= budget * 1.02]
    pool = affordable or candidates

    # Score: prefer affordable, then fewer hops unless hops unlock a cheaper peak,
    # then lower total burn, then sooner first window.
    def score(plan: RoutePlan) -> tuple:
        can = 0 if peak_required(plan) <= budget * 1.02 else 1
        # If direct is unaffordable, strongly prefer hop routes.
        hop_penalty = plan.hop_count if (direct and peak_required(direct) <= budget * 1.02 and not prefer_hops) else 0
        first_wait = plan.legs[0].wait_days if plan.legs else 9999.0
        return (can, hop_penalty, peak_required(plan), plan.total_ms, first_wait)

    pool.sort(key=score)
    best = pool[0]
    # Apply slack: if a hop route is only slightly worse than direct and direct
    # is affordable, keep direct unless prefer_hops and hop peak is lower.
    if direct is not None and best is not direct:
        if peak_required(direct) <= budget * 1.02:
            if peak_required(best) > peak_required(direct) * ROUTE_COST_SLACK and not prefer_hops:
                best = direct
    return best


def route_preview_lines(plan: RoutePlan, bodies: dict) -> list[str]:
    """HUD-friendly lines for the confirm sheet / planner panel."""
    def name(key: str) -> str:
        body = bodies.get(key)
        return body.name if body is not None else key

    lines = [f"ROUTE → {name(plan.destination)}", plan.summary_line(), plan.reason]
    for i, leg in enumerate(plan.legs, 1):
        tag = {"harvest": "HARVEST", "refuel": "REFUEL", "home": "HOME", "transfer": "HOP"}.get(
            leg.purpose, leg.purpose.upper())
        lines.append(
            f"  {i}. {tag:<7} {name(leg.origin)} → {name(leg.destination)}  "
            f"{leg.outbound_ms:,.0f} m/s  wait {leg.wait_days:,.0f}d  TOF {leg.tof_days:,.0f}d"
        )
    return lines


def standing_order_targets(sim, ship, orders: dict[str, Any]) -> str | None:
    """Pick a destination from standing orders (auto-dispatcher helper).

    ``orders`` shape::
        {"mode": "value"|"route", "prefer_hops": bool, "min_depot_fuel": float,
         "destinations": ["deep_belt", "outer_reach", ...]}
    """
    from src.mining import plan_extraction  # local import: avoid cycles at module load

    dests = list(orders.get("destinations") or [])
    if not dests:
        dests = list(getattr(sim, "trade_targets", ()))
    prefer = bool(orders.get("prefer_hops", ROUTE_PREFER_DEPOT_HOPS))
    min_fuel = float(orders.get("min_depot_fuel", 0.0))
    best_key = None
    best_score = -1.0
    for key in dests:
        if key == "colony":
            continue
        plan = plan_route(sim, ship, key, prefer_hops=prefer)
        if plan is None:
            continue
        # Reject hop plans whose depots are bone-dry.
        if not plan.direct:
            dry = False
            for via in plan.via:
                depot = sim.depots.get(via)
                if depot is None or depot.fuel_ms < min_fuel:
                    dry = True
                    break
            if dry:
                continue
        try:
            payload = plan_extraction(
                key, sim.ledger, sim.reserved.get(key),
                capacity_t=ship.capacity, mode=sim.mining_mode,
                mine_bonus=1.0, hull_pct=100.0,
            )
            value = float(sum(payload.values()))
        except Exception:
            value = 1.0
        peak = max((leg.outbound_ms for leg in plan.legs), default=plan.total_ms)
        score = value / max(peak, 1.0)
        if score > best_score:
            best_key, best_score = key, score
    return best_key
