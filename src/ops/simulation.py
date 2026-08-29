"""Fleet operations layered on the verified orbital simulation.

``OpsSimulation`` **subclasses** ``OrbitalSimulation`` rather than modifying
it, so the astrodynamics core in ``src/simulation/orbital_sim.py`` (and the 43
tests that pin it down) stays untouched. This layer adds the economic shell:

* **Ship classes** (scout / freighter / refinery / hauler) from
  ``config.SHIP_CLASSES`` — honest differences in propellant budget, hold
  volume, refuel rate and wear, never a physics discount.
* **Hull wear** charged per burn by diffing ``ship.delta_v`` around each
  super() call, plus core-drilling wear. Low hull refuses dispatch and risks
  incidents; the colony can repair docked ships for credits.
* **Mining**: payloads are planned from each body's procedural ore
  fingerprint (``src/mining.py``), with per-body depletion committed only when
  a capture actually succeeds. In-flight reservations stop two ships from
  selling the same vein twice.
* **Incidents**: seeded rolls at capture can lose part of a delivery when the
  crew drills hard or flies on a tired hull.
* **Crew**: every ship carries a named roster with morale and fatigue.
  Fatigue accumulates in flight and layovers, recovers at the colony; morale
  rises with successful captures and payday, falls with overwork, boredom and
  hardship. Tired or unhappy crews cause incidents and mine less.
* **Space weather**: deterministic solar-flare cycles (quiet -> warning ->
  flare) and periodic debris seasons. Only ships in flight are exposed; both
  add hull wear per day, flares also grind on morale.

The base class remains directly constructible and behaves exactly as before;
every extension here is additive.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

import numpy as np

from src.config import (
    CAMPAIGN_BODIES,
    RIVAL_DUMP_PERIOD_DAYS,
    COMET_ELEMENTS,
    COMET_KEY,
    MINING_EXTRA_SPAWNS,
    CREW_ENGINEER_REPAIR_BONUS,
    CREW_FATIGUE_EXHAUSTED,
    CREW_MORALE_CAPTURE_BONUS,
    CREW_MORALE_MAX,
    DEFAULT_SHIP_CLASS,
    DEBRIS_SEASON_PERIOD_DAYS,
    FLARE_QUIET_DAYS_RANGE,
    HULL_CRITICAL_PCT,
    HULL_MAX_PCT,
    HULL_MIN_PCT,
    HULL_REPAIR_COST_PER_PCT,
    HULL_REPAIR_RATE_PCT_PER_DAY,
    INCIDENT_CHANCE_DRILL,
    INCIDENT_CHANCE_SCRAPE,
    INCIDENT_CARGO_LOSS,
    INCIDENT_LOW_HULL_FACTOR,
    MINING_DRILL_WEAR_PCT,
    MINING_LOW_HULL_YIELD_PCT,
    MINING_RECOVERY_TAU_DAYS,
    MU_SUN,
    PLANNING_MAX_REVS,
    REFINERY_ARRIVAL_BATCHES,
    PLANNING_MULTI_REV_MIN_SAVING,
    PERTURB_MAX_INTERVAL_DAYS,
    PERTURB_MIN_INTERVAL_DAYS,
    SIM_SECONDS_PER_DAY,
)
from src.market import rng_from_json, rng_to_json
from src.maths.elements import OrbitalElements
from src.maths import windows as window_solver
from src.mining import YieldLedger, plan_extraction, register_body_ores, register_extra_spawns
from src.simulation.bodies import BODIES, Body, TRADE_TARGETS
from src.simulation.orbital_sim import Delivery, Leg, LogEntry, Mission, OrbitalSimulation, Ship


# Structures extracted to src/ops/structures.py - keep re-export for backward compat
from src.ops.structures import CrewMember, Depot, Refinery
from src.ops.mixins.crew import CrewMixin
from src.ops.mixins.weather import WeatherMixin
from src.ops.mixins.depot import DepotMixin
from src.ops.mixins.swarm import SwarmMixin
from src.ops.mixins.ships import ShipsMixin


# Roster template per ship: role -> seats. Miners outnumber everyone because
# mining is where the money (and the incidents) come from.
CREW_ROSTER_TEMPLATE = {"pilot": 1, "miner": 2, "engineer": 1}

# Mission legs that keep a crew away from the colony.
_AWAY_LEGS = {Leg.OUTBOUND, Leg.INBOUND, Leg.WAITING, Leg.PENDING}


class OpsSimulation(CrewMixin, WeatherMixin, DepotMixin, SwarmMixin, ShipsMixin, OrbitalSimulation):
    """The verified supply-chain sim plus fleet classes, hulls and mining."""

    def __init__(self, seed: int = 20260826, ship_names: tuple[str, ...] = ("Kestrel",),
                 ship_classes: dict[str, str] | None = None):
        # Consumed by the _parked_ship hook while super().__init__ builds the
        # starting fleet; maps ship name -> class key.
        self._pending_classes = dict(ship_classes or {})
        self.ship_class: dict[str, str] = {}
        self.hull: dict[str, float] = {}
        self.mining_mode = "scrape"          # or "drill"
        self.ledger = YieldLedger()
        #: body -> ore -> tonnes promised to ships currently inbound
        self.reserved: dict[str, dict[str, float]] = {}
        #: ship name -> (body, payload) while the outbound leg is flying
        self._inflight: dict[str, tuple[str, dict[str, float]]] = {}
        self.rng = random.Random(seed ^ 0x5EED)
        #: ship name -> roster of CrewMember
        self.crew: dict[str, list[CrewMember]] = {}
        #: ship name -> installed parts {"tank": n, "drill": n, "quarters": n}
        self.upgrades: dict[str, dict[str, int]] = {}
        #: generic tech multipliers set by the game layer (depot_generation,
        #: refinery, fatigue, hull_wear, refuel_rate) -- the sim never knows
        #: tech or difficulty names, only numbers.
        self.tech_mults: dict[str, float] = {}
        #: hull never drops below this (Ironman can set 0.0 for wrecks)
        self.hull_floor = HULL_MIN_PCT
        #: ship name -> remaining RoutePlan legs (multi-stop delivery)
        self.routes: dict[str, list] = {}
        #: standing auto-dispatch orders (destinations + hop policy)
        self.standing_orders: dict = {"prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}
        #: body_key -> active swarm dict {count, remaining_days, yield_t, launched_day}
        self.swarms: dict[str, dict] = {}
        #: body_key -> sim-day when next swarm is allowed
        self.swarm_cooldown: dict[str, float] = {}
        #: body -> {bonus, expires_day}
        self.survey_bonus: dict[str, dict] = {}
        #: body -> ISRU spike count
        self.isru_spikes: dict[str, int] = {}
        #: body -> {module_key: count}
        self.station_modules: dict[str, dict[str, int]] = {}
        self.rival_enabled = False  # game layer opts in via settings
        self._rival_dump_timer = float(RIVAL_DUMP_PERIOD_DAYS)
        #: body key -> refuel depot (player-built)
        self.depots: dict[str, Depot] = {}
        #: body key -> refinery station (player-built)
        self.refineries: dict[str, Refinery] = {}
        #: the network this campaign flies (extra bodies, e.g. a comet)
        self.trade_targets: tuple[str, ...] = tuple(TRADE_TARGETS)

        #: colony-side botanists (they work the hydroponics racks, not ships)
        self.botanists = 0
        # Gravitational perturbation clock: this sim owns its own body table,
        # so a passing body nudges *this* campaign's orbits and nothing else.
        self._perturb_timer = self.rng.uniform(
            PERTURB_MIN_INTERVAL_DAYS, PERTURB_MAX_INTERVAL_DAYS
        ) * SIM_SECONDS_PER_DAY
        # Multi-rev planning knobs (see config comments).
        self._max_revs = PLANNING_MAX_REVS
        self._multi_rev_min_saving = PLANNING_MULTI_REV_MIN_SAVING
        #: ship name -> sim time of the last departure or docking
        self.last_active: dict[str, float] = {}
        # Space weather state (deterministic, ticked in step()).
        self.flare_state = "quiet"            # quiet | warning | flare
        self._flare_timer = self.rng.uniform(*FLARE_QUIET_DAYS_RANGE) * SIM_SECONDS_PER_DAY
        self._flare_duration = 0.0
        self._debris_timer = DEBRIS_SEASON_PERIOD_DAYS * SIM_SECONDS_PER_DAY
        self.debris_active = False
        # Per-instance knobs so tests can tighten probabilities without
        # touching global config.
        self.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        self.incident_chance_drill = INCIDENT_CHANCE_DRILL
        self.hull_critical_pct = HULL_CRITICAL_PCT
        super().__init__(seed=seed, ship_names=ship_names)
        # Own the body table: perturbations replace entries here instead of
        # mutating the shared module-level BODIES the verified tests read.
        self.bodies = dict(self.bodies)
        self._install_comet()

    def _install_comet(self) -> None:
        """Install campaign-only bodies (comet + deep fields) into this sim copy."""
        self._install_campaign_body_comet()
        self._install_campaign_fields()

    def _install_campaign_body_comet(self) -> None:
        """Add "Vigil", a long-period comet only this campaign can see.

        It lives in the campaign body table; the verified module table stays
        pristine. Called from both ``__init__`` and ``from_json``.
        """
        if COMET_KEY in self.bodies:
            return
        el = OrbitalElements(a=COMET_ELEMENTS["a"], e=COMET_ELEMENTS["e"],
                             i=math.radians(COMET_ELEMENTS["i_deg"]),
                             raan=math.radians(COMET_ELEMENTS["raan_deg"]),
                             argp=math.radians(COMET_ELEMENTS["argp_deg"]),
                             nu=math.radians(COMET_ELEMENTS["nu_deg"]))
        self.bodies[COMET_KEY] = Body(
            key=COMET_KEY, name="Comet Vigil", elements=el,
            radius_km=6.0, soi_km=9000.0,
            palette=(0.72, 0.86, 1.0),
            resources=("ice", "platinum"),
            description="A long-period comet. Rare windows, fast arrival, primordial wealth.",
            render_scale=0.45,
        )
        register_body_ores(COMET_KEY, ("ice", "platinum", "thorite", "aurellium"))
        register_extra_spawns(MINING_EXTRA_SPAWNS)
        if COMET_KEY not in self.trade_targets:
            self.trade_targets = tuple(self.trade_targets) + (COMET_KEY,)
        self.stats.setdefault("incidents", 0)
        self.stats.setdefault("ore_mined_t", 0.0)
        self.stats.setdefault("full_returns", 0)
        self.stats.setdefault("captures_by_body", {})

    # -- construction --------------------------------------------------------
    def _install_campaign_fields(self) -> None:
        """Trojan Field, Cinder Moon, Outer Reach -- multi-hop endgame rocks."""
        for key, spec in CAMPAIGN_BODIES.items():
            if key in self.bodies:
                continue
            el_spec = spec["elements"]
            el = OrbitalElements(
                a=el_spec["a"], e=el_spec["e"],
                i=math.radians(el_spec["i_deg"]),
                raan=math.radians(el_spec["raan_deg"]),
                argp=math.radians(el_spec["argp_deg"]),
                nu=math.radians(el_spec["nu_deg"]),
            )
            self.bodies[key] = Body(
                key=key, name=spec["name"], elements=el,
                radius_km=float(spec["radius_km"]), soi_km=float(spec["soi_km"]),
                palette=tuple(spec["palette"]),
                resources=tuple(spec.get("resources", ())),
                description=str(spec.get("description", "")),
                render_scale=float(spec.get("render_scale", 1.0)),
            )
            register_body_ores(key, tuple(spec.get("resources", ())))
            if key not in self.trade_targets:
                self.trade_targets = tuple(self.trade_targets) + (key,)



    # -- fleet management ----------------------------------------------------



    # -- upgrade parts ---------------------------------------------------------







    # -- wear & maintenance --------------------------------------------------

    def affordable_targets(self, ship: Ship, margin: float = 1.15) -> list[tuple[str, float]]:
        """Campaign-network override of the base affordability scan."""
        affordable: list[tuple[str, float]] = []
        for key in self.trade_targets:
            if key == ship.origin:
                continue
            cost = self.round_trip_cost_ms(ship.origin, key)
            if cost is not None and cost * margin <= ship.delta_v:
                affordable.append((key, cost))
        affordable.sort(key=lambda item: item[1])
        return affordable

    def refuel_docked_fleet(self, dt_days: float) -> float:
        """Per-class refuel rates; otherwise identical to the base rule."""
        granted = 0.0
        for ship in self.ships:
            if ship.name in self.missions or ship.origin != "colony":
                continue
            full = self.effective_delta_v(ship.name)
            headroom = full - ship.delta_v
            if headroom <= 0.0:
                continue
            rate = self.class_spec(ship.name)["refuel_rate"] * float(
                self.tech_mults.get("refuel_rate", 1.0))
            amount = min(headroom, rate * dt_days)
            ship.delta_v += amount
            granted += amount
        return granted

    def repair_docked_fleet(self, dt_days: float, max_credits: float) -> tuple[float, float]:
        """Repair docked ships up to ``max_credits`` spend.

        Returns ``(hull_pct_restored, credits_spent)``.
        """
        restored = 0.0
        spent = 0.0
        budget = max(0.0, max_credits)
        for ship in self.ships:
            if ship.name in self.missions or ship.origin != "colony":
                continue
            deficit = HULL_MAX_PCT - self.hull.get(ship.name, HULL_MAX_PCT)
            if deficit <= 1e-6:
                continue
            rate = HULL_REPAIR_RATE_PCT_PER_DAY
            if self.has_engineer(ship.name):
                rate *= 1.0 + CREW_ENGINEER_REPAIR_BONUS
            amount = min(deficit, rate * dt_days)
            cost = amount * HULL_REPAIR_COST_PER_PCT
            if cost > budget:
                amount *= budget / cost if cost > 0.0 else 0.0
                cost = budget
            if amount <= 1e-6:
                break
            self.hull[ship.name] += amount
            restored += amount
            spent += cost
            budget -= cost
        return restored, spent

    # -- mining-aware dispatch ----------------------------------------------
    def _depot_bond(self, ship: Ship, target_key: str) -> float:
        """Delta-v loan a depot at ``target_key`` can back, or 0.

        Conditions: the ship can reach the target on its own tank (outbound
        window total fits), and the depot tank holds enough to cover the ride
        home that the ship cannot pay for itself.
        """
        depot = self.depots.get(target_key)
        if depot is None:
            return 0.0
        outbound = self.launch_window(ship.origin, target_key)
        if outbound is None:
            return 0.0
        _, return_window = self.plan_round_trip(ship.origin, target_key, max_age=None)
        if return_window is None:
            return 0.0
        out_cost = self.delta_v_km_s(outbound.total_delta_v) * 1000.0
        back_cost = self.delta_v_km_s(return_window.total_delta_v) * 1000.0
        if out_cost > ship.delta_v:
            return 0.0
        shortfall = back_cost - (ship.delta_v - out_cost)
        if shortfall <= 0.0:
            return 0.0
        if depot.fuel_ms < shortfall:
            return 0.0
        return shortfall

    def dispatch(self, ship: Ship, target_key: str, cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        if self.hull.get(ship.name, HULL_MAX_PCT) < self.hull_critical_pct:
            return False, (
                f"{ship.name} is worn to {self.hull[ship.name]:.0f}% hull; "
                "repairs are required before dispatch."
            )
        morale, fatigue = self.crew_stats(ship.name)
        if fatigue > CREW_FATIGUE_EXHAUSTED:
            who = max(self.crew[ship.name], key=lambda member: member.fatigue).name
            return False, (
                f"{ship.name}'s crew is exhausted ({who} at {fatigue:.0f}% fatigue); "
                "they need dock time before another run."
            )
        if cargo is None:
            spec = self.class_spec(ship.name)
            payload = plan_extraction(
                target_key,
                self.ledger,
                self.reserved.get(target_key),
                capacity_t=self.ship_capacity(ship.name),
                mode=self.mining_mode,
                mine_bonus=spec["mine_bonus"] * self.crew_yield_factor(ship.name)
                * self.ship_mine_bonus(ship.name) * self.survey_mult(target_key)
                * self.body_mine_bonus(target_key),
                hull_pct=self.mining_hull(ship),
            )
            if sum(payload.values()) < 1.0:
                return False, (
                    f"The veins at {self.bodies[target_key].name} are worked out; "
                    "the field needs years to recover."
                )
            bond = self._depot_bond(ship, target_key)
            if bond > 0.0:
                # Depot-assisted run: lend the ship the delta-v it will be
                # granted at the depot so the round-trip check passes, then
                # take the loan back -- the ride home comes from the depot
                # tank while the ship waits for the return window.
                ship.delta_v += bond
                try:
                    ok, message = super().dispatch(ship, target_key, cargo=payload)
                finally:
                    ship.delta_v -= bond
                if ok:
                    depot = self.depots[target_key]
                    self.note(
                        f"{ship.name} plans a depot-supported run to "
                        f"{self.bodies[target_key].name} "
                        f"({depot.fuel_ms:,.0f} m/s in the tank)."
                    )
                    slot = self.reserved.setdefault(target_key, {})
                    for ore, tonnes in payload.items():
                        slot[ore] = slot.get(ore, 0.0) + tonnes
                    self._inflight[ship.name] = (target_key, dict(payload))
                return ok, message
            ok, message = super().dispatch(ship, target_key, cargo=payload)
            if ok:
                slot = self.reserved.setdefault(target_key, {})
                for ore, tonnes in payload.items():
                    slot[ore] = slot.get(ore, 0.0) + tonnes
                self._inflight[ship.name] = (target_key, dict(payload))
                mission = self.missions.get(ship.name)
                if mission is not None and mission.return_window is not None:
                    revs = max(getattr(mission.return_window, "revs", 0), 0)
                    if revs >= 1:
                        self.note(
                            f"{ship.name} flies a {revs}-revolution slow route "
                            f"(propellant over pace)."
                        )
            return ok, message
        return super().dispatch(ship, target_key, cargo=cargo)

    def _release_reservation(self, body_key: str, payload: dict[str, float]) -> None:
        slot = self.reserved.get(body_key)
        if slot is None:
            return
        for ore, tonnes in payload.items():
            slot[ore] = max(0.0, slot.get(ore, 0.0) - tonnes)
        if all(v <= 1e-9 for v in slot.values()):
            self.reserved.pop(body_key, None)

    def recover_mines(self, dt_days: float) -> None:
        self.ledger.recover(dt_days, MINING_RECOVERY_TAU_DAYS)


    # -- multi-stop delivery planner -------------------------------------------
    def plan_delivery(self, ship: Ship, target_key: str, prefer_hops: bool | None = None):
        """Return the best RoutePlan for ``ship`` → ``target_key`` (or None)."""
        from src.routes import plan_route
        if prefer_hops is None:
            prefer_hops = bool(self.standing_orders.get("prefer_hops", True))
        return plan_route(self, ship, target_key, prefer_hops=prefer_hops)

    def dispatch_route(self, ship: Ship, target_key: str,
                       cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        """Dispatch using the multi-stop planner when a direct run will not fit.

        Direct-capable runs still go through the normal single-leg dispatch.
        Otherwise the first hop is flown now and the remaining legs are queued
        on ``self.routes[ship.name]``; each completed hop auto-continues.
        """
        from src.routes import plan_route, route_preview_lines

        if ship.name in self.missions:
            return False, f"{ship.name} is already flying a mission."
        plan = plan_route(self, ship, target_key)
        if plan is None:
            return False, f"No route to {self.bodies.get(target_key, target_key)}."
        if plan.direct or plan.hop_count == 0:
            return self.dispatch(ship, target_key, cargo=cargo)

        # Multi-hop: fly the first leg; queue the rest.
        first = plan.legs[0]
        if first.purpose == "harvest":
            ok, message = self.dispatch(ship, first.destination, cargo=cargo)
        else:
            # Pure transfer / refuel hop: fly empty so veins are not reserved.
            ok, message = super().dispatch(ship, first.destination, cargo={"ice": 0.01})
            if ok:
                ship.cargo = {}
                mission = self.missions.get(ship.name)
                if mission is not None:
                    mission.cargo = {}
                self._inflight.pop(ship.name, None)
        if not ok:
            return False, message
        # Stash remaining legs (after the one just started).
        remaining = list(plan.legs[1:])
        self.routes[ship.name] = remaining
        via = "/".join(self.bodies[k].name if k in self.bodies else k for k in plan.via)
        self.note(
            f"{ship.name} flies a multi-stop harvest to "
            f"{self.bodies[target_key].name} via {via} "
            f"({plan.hop_count} hop(s), {plan.total_ms:,.0f} m/s billed)."
        )
        preview = route_preview_lines(plan, self.bodies)
        return True, f"{ship.name} multi-stop: {preview[1]}"

    def _continue_route(self, ship: Ship) -> None:
        """After a hop completes, launch the next queued leg if any."""
        queue = self.routes.get(ship.name) or []
        if not queue:
            self.routes.pop(ship.name, None)
            return
        if ship.name in self.missions:
            return
        nxt = queue.pop(0)
        self.routes[ship.name] = queue
        purpose = nxt.purpose
        dest = nxt.destination
        # Top up from a depot if we are sitting on one.
        depot = self.depots.get(ship.origin)
        if depot is not None:
            full = self.effective_delta_v(ship.name)
            headroom = full - ship.delta_v
            draw = min(headroom, depot.fuel_ms)
            if draw > 1.0:
                ship.delta_v += draw
                depot.fuel_ms -= draw
                self.note(
                    f"{ship.name} tops up at {self.bodies[ship.origin].name} "
                    f"depot (+{draw:,.0f} m/s) before the next hop."
                )
        if purpose == "harvest":
            ok, message = self.dispatch(ship, dest, cargo=None)  # let dispatch plan extraction
        else:
            ok, message = super().dispatch(ship, dest, cargo={"ice": 0.0})
            if ok:
                ship.cargo = {}
                mission = self.missions.get(ship.name)
                if mission is not None:
                    mission.cargo = {}
                self._inflight.pop(ship.name, None)
        if ok:
            self.note(f"{ship.name} continues route: {purpose} → {self.bodies.get(dest, dest).name if dest in self.bodies else dest}.")
        else:
            self.note(f"{ship.name} route stalled at {ship.origin}: {message}")
            self.routes.pop(ship.name, None)












    # -- harvest drone swarms (window GO moment) --------------------------------




    # -- refuel depots ---------------------------------------------------------


    # -- refinery stations -------------------------------------------------------








    # -- crew ----------------------------------------------------------------





    # -- crew specialisations -----------------------------------------------







    # -- space weather ---------------------------------------------------------

    # -- gravitational perturbations ------------------------------------------


    # -- multi-rev-aware window planning ---------------------------------------
    def _solve_window(self, origin_key: str, target_key: str, *,
                      epoch: float, min_departure_time: float | None = None,
                      max_departure_time: float | None = None):
        """Window search including multi-rev branches when they pay off."""
        from src.config import WINDOW_GRID_DEPART, WINDOW_GRID_TOF

        return window_solver.solve_window_multi(
            self.bodies[origin_key].elements, self.bodies[target_key].elements, MU_SUN,
            origin_key=origin_key, target_key=target_key,
            n_depart=WINDOW_GRID_DEPART, n_tof=WINDOW_GRID_TOF,
            epoch=epoch, min_departure_time=min_departure_time,
            max_departure_time=max_departure_time,
            max_revs=self._max_revs,
            multi_rev_min_saving=self._multi_rev_min_saving,
        )

    def launch_window(self, origin_key: str, target_key: str, refresh: bool = False):
        """Multi-rev-aware override of the cached window lookup."""
        cache_key = (origin_key, target_key)
        if not refresh and cache_key in self._window_cache:
            cached = self._window_cache[cache_key]
            if cached.departure_time >= self.time - 1e-9:
                return cached
        window = self._solve_window(origin_key, target_key, epoch=self.time,
                                    min_departure_time=self.time)
        if window is not None:
            self._window_cache[cache_key] = window
            self.stats["windows_solved"] += 1
        return window

    def plan_round_trip(self, origin_key: str, target_key: str, max_age: float | None = None):
        """Multi-rev-aware override of the round-trip planner.

        Semantics mirror the base implementation (cache with TTL, stale
        outbound re-solved from now, inbound bounded below by arrival) but
        every window search may consider multi-rev branches.
        """
        # Core semantics: ``max_age=None`` means "fresh pricing" (no cache
        # read) -- dispatch depends on that; a TTL is passed by callers that
        # merely want a recent estimate.
        cache_key = (origin_key, target_key)
        if max_age is not None:
            cached = self._round_trip_cache.get(cache_key)
            if cached is not None and (self.time - cached[0]) < max_age:
                return cached[1], cached[2]

        outbound = self.launch_window(origin_key, target_key)
        if outbound is None:
            return None, None
        if outbound.departure_time < self.time - 1e-9:
            outbound = self._solve_window(origin_key, target_key, epoch=self.time,
                                          min_departure_time=self.time)
            if outbound is None:
                return None, None
        arrival = outbound.departure_time + outbound.tof
        inbound = self._solve_window(target_key, origin_key, epoch=arrival,
                                     min_departure_time=arrival)
        if inbound is not None:
            self._round_trip_cache[cache_key] = (self.time, outbound, inbound)
        return outbound, inbound

    # -- stepping --------------------------------------------------------------
    def step(self, dt_days: float) -> list[LogEntry]:
        """Tick the ops layer (crew, weather) on top of the base event step.

        The base class processes mission events at their exact instants; the
        crew and weather ticks apply their per-day rates across the whole
        ``dt_days``, which is exact enough at the step sizes the game runs.
        """
        entries = super().step(dt_days)
        self.tick_weather(dt_days)
        self.tick_crew(dt_days)
        self.tick_perturbations(dt_days)
        self.tick_depots(dt_days)
        self._depot_refuel_waiting(dt_days)
        self._tanker_fill_depot(dt_days)
        self._depot_drones_load(dt_days)
        self._refinery_smelt_waiting(dt_days)
        self.tick_swarms(dt_days)
        self.tick_rival(dt_days)
        # Observatories grant RP via stats side-channel for the game layer.
        rp = self.tick_observatories(dt_days)
        if rp > 0.0:
            self.stats["observatory_rp"] = float(self.stats.get("observatory_rp", 0.0)) + rp
        return entries

    # -- mission hooks (wear, depletion, incidents) --------------------------
    def _pilot_refund(self, ship: Ship, spent_ms: float) -> None:
        """Hand back the pilot discount on a burn the core just billed."""
        if spent_ms <= 0.0:
            return
        ship.delta_v += spent_ms * self.pilots_discount(ship.name)

    def _depart(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._depart(ship, mission)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))
        self.last_active[ship.name] = self.time

    def _depot_topup_on_arrival(self, ship: Ship, mission: Mission) -> None:
        """Docking at a depot body: draw the ride home from its tank.

        The base class checks return-leg affordability at the capture instant,
        so the fuel the ship needs has to be in its tank *before* that check
        runs -- this is the gas-station stop, not a trickle.
        """
        depot = self.depots.get(mission.target)
        if depot is None or mission.return_window is None:
            return
        target = self.bodies[mission.target]
        _, v_target = window_solver.body_state(target.elements, MU_SUN, self.time)
        _, v_ship = ship.state_at(self.time)
        dv_match_ms = self.delta_v_km_s(float(np.linalg.norm(v_ship - v_target))) * 1000.0
        if dv_match_ms > ship.delta_v:
            return  # the capture itself will fail; nothing to service yet
        need = self.delta_v_km_s(mission.return_window.total_delta_v) * 1000.0
        shortfall = max(0.0, need - (ship.delta_v - dv_match_ms))
        headroom = self.class_spec(ship.name)["delta_v"] - ship.delta_v
        draw = min(headroom, depot.fuel_ms, shortfall + 2000.0)
        if draw > 0.0:
            ship.delta_v += draw
            depot.fuel_ms -= draw
            self.note(
                f"{ship.name} refuels at the {self.bodies[mission.target].name} depot "
                f"(+{draw:,.0f} m/s, {depot.fuel_ms:,.0f} m/s left)."
            )

    def _smelt_hold(self, ship: Ship, body_key: str, batches: int) -> int:
        """Run up to ``batches`` smelting passes over a hold; returns runs."""
        refinery = self.refineries.get(body_key)
        if refinery is None:
            return 0
        done = 0
        for _ in range(batches):
            recipe = self._first_craftable_recipe(ship)
            if recipe is None:
                break
            for ore, amount in recipe["input"].items():
                ship.cargo[ore] = ship.cargo.get(ore, 0.0) - amount
            ship.cargo[recipe["output"]] = ship.cargo.get(recipe["output"], 0.0) + recipe["amount"]
            refinery.batches_done += 1
            done += 1
        return done

    def _capture(self, ship: Ship, mission: Mission, target) -> None:
        if mission.leg is Leg.OUTBOUND:
            self._depot_topup_on_arrival(ship, mission)
            if self.refineries.get(mission.target) is not None:
                smelted = self._smelt_hold(ship, mission.target, REFINERY_ARRIVAL_BATCHES)
                if smelted:
                    self.note(
                        f"{ship.name}'s ore is smelted at the "
                        f"{self.bodies[mission.target].name} refinery "
                        f"({smelted} batches: {dict((k, round(v, 1)) for k, v in ship.cargo.items() if v > 0)})."
                    )
        inflight = self._inflight.pop(ship.name, None)
        before = ship.delta_v
        super()._capture(ship, mission, target)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))

        # Multi-stop transfer: after arriving at a hop body, chain the next leg
        # instead of flying the auto-return the core planned.
        if mission.leg is Leg.WAITING and self.routes.get(ship.name):
            # Only chain when this arrival was a hop (queue still has legs).
            if self._abort_return_and_continue(ship, mission):
                return

        delivered_now = (
            len(self.pending_deliveries) > 0
            and self.pending_deliveries[-1].ship == ship.name
            and abs(self.pending_deliveries[-1].time - self.time) < 1e-9
        )
        if inflight is None:
            return
        body_key, payload = inflight
        if not delivered_now:
            # Run failed (fly-past, no return plan): the ore was never mined,
            # so the vein is released rather than drawn down.
            self._release_reservation(body_key, payload)
            return

        # Success: draw the vein down, pay the crew's pride, charge drilling.
        self.ledger.commit(body_key, payload)
        self.stats["ore_mined_t"] += sum(payload.values())
        self.stats["captures_by_body"][body_key] = self.stats["captures_by_body"].get(body_key, 0) + 1
        if self.pending_deliveries:
            delivered_total = float(sum(self.pending_deliveries[-1].cargo.values()))
            if delivered_total >= ship.capacity * 0.98:
                self.stats["full_returns"] += 1
        self.last_active[ship.name] = self.time
        for member in self.crew.get(ship.name, []):
            member.morale = min(CREW_MORALE_MAX, member.morale + CREW_MORALE_CAPTURE_BONUS)
        if self.mining_mode == "drill":
            self.hull[ship.name] = max(
                HULL_MIN_PCT, self.hull[ship.name] - MINING_DRILL_WEAR_PCT
            )

        # Incident roll: drilling is riskier, a tired hull riskier still, and
        # an exhausted or sullen crew multiplies all of it.
        chance = self.incident_chance_drill if self.mining_mode == "drill" else self.incident_chance_scrape
        chance += INCIDENT_LOW_HULL_FACTOR * max(0.0, MINING_LOW_HULL_YIELD_PCT - self.hull[ship.name]) / 100.0
        chance *= self.crew_incident_factor(ship.name)
        if self.rng.random() < chance:
            delivery = self.pending_deliveries[-1]
            lost_total = 0.0
            for ore, tonnes in list(delivery.cargo.items()):
                lost = tonnes * INCIDENT_CARGO_LOSS
                delivery.cargo[ore] = tonnes - lost
                lost_total += lost
            self.stats["mass_delivered"] -= lost_total
            self.stats["incidents"] += 1
            self.note(
                f"Mining incident aboard {ship.name} at {self.bodies[body_key].name}: "
                f"{lost_total:.0f} t of ore lost ({self.hull[ship.name]:.0f}% hull)."
            )
        self._release_reservation(body_key, payload)


    def _abort_return_and_continue(self, ship: Ship, mission: Mission) -> bool:
        """If a multi-stop queue remains, cancel the auto-return and hop onward."""
        queue = self.routes.get(ship.name) or []
        if not queue:
            return False
        # Ship is WAITING at mission.target with a return_window home -- drop it.
        if ship.name in self.missions:
            # Treat capture as a successful hop endpoint; clear mission so we can re-dispatch.
            # Mass already counted by core if cargo was delivered; transfer hops had empty cargo.
            self.missions.pop(ship.name, None)
        ship.origin = mission.target
        self._continue_route(ship)
        return True

    def _complete_run(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._complete_run(ship, mission)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))
        self.last_active[ship.name] = self.time
        # Multi-stop: if more legs remain, depart the next hop immediately.
        if self.routes.get(ship.name):
            self._continue_route(ship)

    # -- reporting -----------------------------------------------------------
    def ship_report(self, ship: Ship) -> dict:
        report = super().ship_report(ship)
        report["class"] = self.ship_class.get(ship.name, DEFAULT_SHIP_CLASS)
        report["hull"] = self.hull.get(ship.name, HULL_MAX_PCT)
        report["capacity"] = ship.capacity
        report["dv_max"] = self.effective_delta_v(ship.name)
        report["parts"] = dict(self.upgrades.get(ship.name, {}))
        return report

    # -- persistence ---------------------------------------------------------
    def to_json(self) -> dict:
        ships = []
        for ship in self.ships:
            ships.append({
                "name": ship.name,
                "class": self.ship_class.get(ship.name, DEFAULT_SHIP_CLASS),
                "hull": self.hull.get(ship.name, HULL_MAX_PCT),
                "origin": ship.origin,
                "epoch": ship.epoch,
                "r": np.asarray(ship.r, dtype=float).tolist(),
                "v": np.asarray(ship.v, dtype=float).tolist(),
                "delta_v": ship.delta_v,
                "cargo": dict(ship.cargo),
                "capacity": ship.capacity,
                "upgrades": dict(self.upgrades.get(ship.name, {})),
            })

        def window_json(window) -> dict | None:
            if window is None:
                return None
            return {
                "departure_time": window.departure_time,
                "tof": window.tof,
                "dv_depart": window.dv_depart,
                "dv_arrive": window.dv_arrive,
                "target_key": window.target_key,
                "origin_key": window.origin_key,
                "miss_distance": window.miss_distance,
                "r1": np.asarray(window.r1).tolist(),
                "v1": np.asarray(window.v1).tolist(),
                "r2": np.asarray(window.r2).tolist(),
                "v2": np.asarray(window.v2).tolist(),
                "v1_body": np.asarray(window.v1_body).tolist(),
                "v2_body": np.asarray(window.v2_body).tolist(),
                "revs": int(getattr(window, "revs", 0)),
            }

        missions = {}
        for name, mission in self.missions.items():
            missions[name] = {
                "target": mission.target,
                "cargo": dict(mission.cargo),
                "departure_time": mission.departure_time,
                "tof": mission.tof,
                "dv_depart": mission.dv_depart,
                "dv_arrive": mission.dv_arrive,
                "r_depart": np.asarray(mission.r_depart).tolist(),
                "v_depart": np.asarray(mission.v_depart).tolist(),
                "leg": mission.leg.value,
                "return_window": window_json(mission.return_window),
            }

        deliveries = [
            {"ship": d.ship, "body": d.body, "time": d.time, "cargo": dict(d.cargo)}
            for d in self.pending_deliveries
        ]
        return {
            "time": self.time,
            "warp_days_per_second": self.warp_days_per_second,
            "next_scan_time": self._next_scan_time,
            "stats": dict(self.stats),
            "log": [{"time": e.time, "text": e.text} for e in self.log],
            "ships": ships,
            "missions": missions,
            "pending_deliveries": deliveries,
            "mining_mode": self.mining_mode,
            "ledger": self.ledger.to_json(),
            "reserved": {body: dict(slot) for body, slot in self.reserved.items()},
            "inflight": {name: [body, payload] for name, (body, payload) in self._inflight.items()},
            "crew": {name: [member.to_json() for member in roster]
                     for name, roster in self.crew.items()},
            "depots": [depot.to_json() for depot in self.depots.values()],
            "tech_mults": dict(self.tech_mults),
            "routes": {name: [leg.__dict__ if hasattr(leg, "__dict__") else leg for leg in legs]
                       for name, legs in self.routes.items()},
            "standing_orders": dict(self.standing_orders),
            "swarms": {k: dict(v) for k, v in self.swarms.items()},
            "swarm_cooldown": dict(self.swarm_cooldown),
            "survey_bonus": {k: dict(v) for k, v in self.survey_bonus.items()},
            "isru_spikes": dict(self.isru_spikes),
            "station_modules": {k: dict(v) for k, v in self.station_modules.items()},
            "rival_enabled": bool(self.rival_enabled),
            "rival_dump_timer": float(getattr(self, "_rival_dump_timer", RIVAL_DUMP_PERIOD_DAYS)),
            "hull_floor": float(getattr(self, "hull_floor", HULL_MIN_PCT)),
            "refineries": [r.to_json() for r in self.refineries.values()],
            "botanists": self.botanists,
            "perturb_timer": self._perturb_timer,
            "body_overrides": {
                key: {"a": body.elements.a, "e": body.elements.e}
                for key, body in self.bodies.items()
                if body is not BODIES.get(key)
            },
            "last_active": dict(self.last_active),
            "weather": {
                "flare_state": self.flare_state,
                "flare_timer": self._flare_timer,
                "flare_duration": self._flare_duration,
                "debris_timer": self._debris_timer,
                "debris_active": self.debris_active,
            },
            "rng": rng_to_json(self.rng),
            "version": 2,
        }

    @classmethod
    def from_json(cls, data: dict) -> "OpsSimulation":
        sim = cls.__new__(cls)
        sim.time = float(data["time"])
        sim.warp_days_per_second = float(data["warp_days_per_second"])
        sim.bodies = dict(BODIES)
        for key, override in data.get("body_overrides", {}).items():
            body = sim.bodies.get(key)
            if body is not None:
                el = body.elements
                sim.bodies[key] = replace(body, elements=OrbitalElements(
                    a=float(override["a"]), e=float(override["e"]),
                    i=el.i, raan=el.raan, argp=el.argp, nu=el.nu))
        sim.ships = []
        sim.missions = {}
        sim.log = []
        sim._window_cache = {}
        sim._round_trip_cache = {}
        sim._next_scan_time = float(data["next_scan_time"])
        sim.stats = dict(data["stats"])
        sim.stats.setdefault("full_returns", 0)
        sim.stats.setdefault("captures_by_body", {})
        sim.pending_deliveries = []
        sim.ship_class = {}
        sim.hull = {}
        # Per-instance knobs normally assigned in __init__; __new__ skips it.
        sim.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        sim.incident_chance_drill = INCIDENT_CHANCE_DRILL
        sim.hull_critical_pct = HULL_CRITICAL_PCT
        sim._max_revs = PLANNING_MAX_REVS
        sim._multi_rev_min_saving = PLANNING_MULTI_REV_MIN_SAVING
        sim.crew = {}
        sim.upgrades = {}
        sim.tech_mults = {}
        sim.routes = {}
        sim.standing_orders = {"prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}
        sim.swarms = {}
        sim.swarm_cooldown = {}
        sim.survey_bonus = {}
        sim.isru_spikes = {}
        sim.station_modules = {}
        sim.rival_enabled = False
        sim._rival_dump_timer = float(RIVAL_DUMP_PERIOD_DAYS)
        sim.last_active = {}
        sim.trade_targets = tuple(TRADE_TARGETS)
        sim.bodies = dict(sim.bodies)
        sim._install_comet()
        sim.depots = {d["body_key"]: Depot.from_json(d) for d in data.get("depots", [])}
        sim.tech_mults = {k: float(v) for k, v in data.get("tech_mults", {}).items()}
        sim.hull_floor = float(data.get("hull_floor", HULL_MIN_PCT))
        from src.routes import RouteLeg
        sim.routes = {}
        for name, legs in data.get("routes", {}).items():
            sim.routes[name] = [RouteLeg(**leg) if isinstance(leg, dict) else leg for leg in legs]
        sim.standing_orders = dict(data.get("standing_orders", {
            "prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}))
        sim.swarms = {k: dict(v) for k, v in data.get("swarms", {}).items()}
        sim.swarm_cooldown = {k: float(v) for k, v in data.get("swarm_cooldown", {}).items()}
        sim.survey_bonus = {k: dict(v) for k, v in data.get("survey_bonus", {}).items()}
        sim.isru_spikes = {k: int(v) for k, v in data.get("isru_spikes", {}).items()}
        sim.station_modules = {k: {mk: int(mv) for mk, mv in v.items()}
                               for k, v in data.get("station_modules", {}).items()}
        sim.rival_enabled = bool(data.get("rival_enabled", False))
        sim._rival_dump_timer = float(data.get("rival_dump_timer", RIVAL_DUMP_PERIOD_DAYS))
        sim.refineries = {r["body_key"]: Refinery.from_json(r) for r in data.get("refineries", [])}
        sim.botanists = int(data.get("botanists", 0))
        sim._perturb_timer = float(data.get("perturb_timer",
                                            PERTURB_MIN_INTERVAL_DAYS * SIM_SECONDS_PER_DAY))
        sim.mining_mode = data["mining_mode"]
        sim.ledger = YieldLedger.from_json(data["ledger"])
        sim.reserved = {body: {ore: float(t) for ore, t in slot.items()}
                        for body, slot in data["reserved"].items()}
        sim._inflight = {name: (body, {ore: float(t) for ore, t in payload.items()})
                         for name, (body, payload) in data["inflight"].items()}

        rng_state = data["rng"]
        sim.rng = rng_from_json(rng_state)

        for entry in data["log"]:
            sim.log.append(LogEntry(float(entry["time"]), entry["text"]))

        for ship_data in data["ships"]:
            ship = Ship(
                name=ship_data["name"],
                origin=ship_data["origin"],
                r=np.array(ship_data["r"], dtype=float),
                v=np.array(ship_data["v"], dtype=float),
                epoch=float(ship_data["epoch"]),
                delta_v=float(ship_data["delta_v"]),
                cargo={ore: float(t) for ore, t in ship_data["cargo"].items()},
                capacity=float(ship_data["capacity"]),
            )
            sim.ships.append(ship)
            sim.ship_class[ship.name] = ship_data["class"]
            sim.hull[ship.name] = float(ship_data["hull"])
            sim.upgrades[ship.name] = {k: int(v) for k, v in ship_data.get("upgrades", {}).items()}

        # Crew rosters; falls back to fresh hires for saves from older
        # versions that predate the crew system.
        for name, roster in data.get("crew", {}).items():
            sim.crew[name] = [CrewMember.from_json(member) for member in roster]
        for ship in sim.ships:
            if ship.name not in sim.crew:
                sim._hire_crew(ship.name)
        sim.last_active = {name: float(t) for name, t in data.get("last_active", {}).items()}

        weather = data.get("weather", {})
        sim.flare_state = weather.get("flare_state", "quiet")
        sim._flare_timer = float(weather.get("flare_timer", FLARE_QUIET_DAYS_RANGE[0] * SIM_SECONDS_PER_DAY))
        sim._flare_duration = float(weather.get("flare_duration", 0.0))
        sim._debris_timer = float(weather.get("debris_timer", DEBRIS_SEASON_PERIOD_DAYS * SIM_SECONDS_PER_DAY))
        sim.debris_active = bool(weather.get("debris_active", False))

        def window_from(w) -> window_solver.LaunchWindow | None:
            if w is None:
                return None
            return window_solver.LaunchWindow(
                departure_time=float(w["departure_time"]),
                tof=float(w["tof"]),
                dv_depart=float(w["dv_depart"]),
                dv_arrive=float(w["dv_arrive"]),
                target_key=w["target_key"],
                origin_key=w["origin_key"],
                miss_distance=float(w["miss_distance"]),
                r1=np.array(w["r1"], dtype=float),
                v1=np.array(w["v1"], dtype=float),
                r2=np.array(w["r2"], dtype=float),
                v2=np.array(w["v2"], dtype=float),
                v1_body=np.array(w["v1_body"], dtype=float),
                v2_body=np.array(w["v2_body"], dtype=float),
                revs=int(w.get("revs", 0)),
            )

        for name, m in data["missions"].items():
            sim.missions[name] = Mission(
                target=m["target"],
                cargo={ore: float(t) for ore, t in m["cargo"].items()},
                departure_time=float(m["departure_time"]),
                tof=float(m["tof"]),
                dv_depart=float(m["dv_depart"]),
                dv_arrive=float(m["dv_arrive"]),
                r_depart=np.array(m["r_depart"], dtype=float),
                v_depart=np.array(m["v_depart"], dtype=float),
                return_window=window_from(m["return_window"]),
                leg=Leg(m["leg"]),
            )

        sim.pending_deliveries = [
            Delivery(ship=d["ship"], body=d["body"], time=float(d["time"]),
                     cargo={ore: float(t) for ore, t in d["cargo"].items()})
            for d in data["pending_deliveries"]
        ]
        return sim
