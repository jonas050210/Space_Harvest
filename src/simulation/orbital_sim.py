"""Patched-conic mission simulation: freighters, burns and supply runs.

This module has no graphics imports at all, so the whole economy can be
simulated headless and unit-tested. ``src/main.py`` only renders whatever
``OrbitalSimulation`` reports.

Flight model
------------
Between burns a ship is propagated analytically with the universal Kepler
solver, so there is no integration drift no matter how large the time step.
Each leg of a run is a patched conic:

1. depart  -- burn onto a Lambert solution that intercepts the moving target,
2. cruise  -- pure two-body propagation along that conic,
3. capture -- burn to match the target's velocity inside its sphere of
   influence, unload cargo,
4. return  -- a fresh window is solved from the target back to the colony.

The capture burn is the classic ``|v_ship - v_body|`` match, which is what
makes an expensive window expensive: arrive fast and you pay for it in
propellant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..config import (
    MU_SUN,
    ROUND_TRIP_CACHE_DAYS,
    SHIP_CARGO_CAPACITY,
    SHIP_START_DELTA_V,
    SIM_SECONDS_PER_DAY,
    TIME_WARP_STEPS,
    DEFAULT_TIME_WARP_DAYS_PER_SECOND,
    AU_PER_YEAR_TO_KM_S,
    SHIP_REFUEL_RATE,
    WINDOW_GRID_DEPART,
    WINDOW_GRID_TOF,
)
from .bodies import BODIES, TRADE_TARGETS, Body
from ..maths import windows as window_solver
from ..maths.kepler import state_energy, universal_kepler


class Leg(str, Enum):
    """Which patched conic the ship is currently flying."""

    PARKED = "parked"
    PENDING = "pending"      # window chosen, waiting for the departure date
    OUTBOUND = "outbound"
    CAPTURE = "capture"
    WAITING = "waiting"      # cargo delivered, holding at the target until the return window opens
    INBOUND = "inbound"


@dataclass
class Ship:
    """A colony freighter flying heliocentric arcs."""

    name: str
    origin: str
    r: np.ndarray                     # heliocentric position, AU
    v: np.ndarray                     # heliocentric velocity, AU / sim-s
    epoch: float                      # sim time the stored state refers to
    delta_v: float = SHIP_START_DELTA_V
    cargo: dict[str, float] = field(default_factory=dict)
    capacity: float = SHIP_CARGO_CAPACITY

    def state_at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Analytically propagate the stored state to time ``t``."""
        return universal_kepler(self.r, self.v, t - self.epoch, MU_SUN)

    def ride_with(self, body: "Body", t: float) -> None:
        """Stay co-orbiting ``body`` -- used while waiting for a return window."""
        from ..maths import windows as _ws

        self.r, self.v = _ws.body_state(body.elements, MU_SUN, t)
        self.epoch = t

    def anchor(self, t: float) -> None:
        """Re-anchor the stored state at ``t`` (called after each burn)."""
        self.r, self.v = self.state_at(t)
        self.epoch = t

    @property
    def cargo_load(self) -> float:
        return float(sum(self.cargo.values()))

    @property
    def speed_km_s(self) -> float:
        """Heliocentric speed in km/s (``v`` is stored in AU/year)."""
        return float(np.linalg.norm(self.v)) * AU_PER_YEAR_TO_KM_S


@dataclass
class Mission:
    """One dispatched supply run.

    ``r_depart`` / ``v_depart`` are held until the departure date because the
    cheapest window is generally *not* right now -- burning early means flying
    a different conic than the one that was planned and paying for it at
    arrival.
    """

    target: str
    cargo: dict[str, float]
    departure_time: float
    tof: float
    dv_depart: float
    dv_arrive: float
    r_depart: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v_depart: np.ndarray = field(default_factory=lambda: np.zeros(3))
    # The return leg is planned at dispatch time rather than improvised on
    # arrival, so the crew knows before leaving whether they can come home.
    return_window: object = None
    leg: Leg = Leg.PENDING


@dataclass
class LogEntry:
    time: float
    text: str


@dataclass
class Delivery:
    """Cargo unloaded by a freighter, waiting to be booked into the colony."""

    ship: str
    body: str
    time: float
    cargo: dict[str, float]

    @property
    def total(self) -> float:
        return float(sum(self.cargo.values()))


class OrbitalSimulation:
    """Owns the clock, the fleet and the window cache."""

    def __init__(self, seed: int = 20260826, ship_names: tuple[str, ...] = ("Kestrel",)):
        self.time = 0.0
        self.warp_days_per_second = DEFAULT_TIME_WARP_DAYS_PER_SECOND
        self.bodies = BODIES
        self.ships: list[Ship] = []
        self.missions: dict[str, Mission] = {}
        self.log: list[LogEntry] = []
        self._window_cache: dict[tuple[str, str], window_solver.LaunchWindow] = {}
        # Round-trip costs are expensive (each one re-solves a Lambert grid),
        # so they are cached with a time-to-live measured in simulation time.
        self._round_trip_cache: dict[tuple[str, str], tuple[float, float]] = {}
        self._next_scan_time = 0.0

        for name in ship_names:
            self.ships.append(self._parked_ship(name, "colony"))

        self.stats = {
            "runs_completed": 0,
            "mass_delivered": 0.0,
            "delta_v_spent": 0.0,
            "windows_solved": 0,
        }
        #: Deliveries produced by ``step`` that the caller has not booked yet.
        self.pending_deliveries: list[Delivery] = []

    # -- construction helpers ----------------------------------------------
    def _parked_ship(self, name: str, body_key: str) -> Ship:
        body = self.bodies[body_key]
        r, v = window_solver.body_state(body.elements, MU_SUN, 0.0)
        return Ship(name=name, origin=body_key, r=r.copy(), v=v.copy(), epoch=0.0)

    def note(self, text: str) -> None:
        self.log.append(LogEntry(self.time, text))
        if len(self.log) > 200:
            del self.log[: len(self.log) - 200]

    def plan_round_trip(self, origin_key: str, target_key: str, max_age: float | None = None):
        """Build an outbound window and a concrete return plan.

        Returns ``(outbound_window, return_window)`` or ``(None, None)``. The
        return window is solved at the *predicted arrival time*, not at the
        current epoch, because that is when the return burn will actually
        happen -- solving it from ``now`` misprices the trip and is how ships
        end up stranded.

        Results are cached per body pair. ``max_age=None`` forces a fresh
        solve, which is what ``dispatch`` does so a committed mission is
        always priced on the plan it will actually fly.
        """
        cache_key = (origin_key, target_key)
        if max_age is not None:
            cached = self._round_trip_cache.get(cache_key)
            if cached is not None and (self.time - cached[0]) < max_age:
                return cached[1], cached[2]

        outbound = self.launch_window(origin_key, target_key)
        if outbound is None:
            return None, None
        if outbound.departure_time < self.time - 1e-9:
            # The cached outbound window has already closed; re-solve it from
            # now so the plan and the burn agree on the departure date.
            outbound = window_solver.solve_window(
                self.bodies[origin_key].elements, self.bodies[target_key].elements, MU_SUN,
                origin_key=origin_key, target_key=target_key,
                epoch=self.time, min_departure_time=self.time,
            )
            if outbound is None:
                return None, None
        arrival = outbound.departure_time + outbound.tof
        # The return leg cannot leave before the ship has arrived, so the
        # search is bounded below by the arrival instant. Without that bound
        # the cheapest grid node can be months in the past, which hands the
        # crew a departure date they can never make.
        inbound = window_solver.solve_window(
            self.bodies[target_key].elements, self.bodies[origin_key].elements, MU_SUN,
            origin_key=target_key, target_key=origin_key,
            epoch=arrival, min_departure_time=arrival,
        )
        if inbound is not None:
            self._round_trip_cache[cache_key] = (self.time, outbound, inbound)
        return outbound, inbound

    def round_trip_cost_ms(self, origin_key: str, target_key: str, max_age: float = ROUND_TRIP_CACHE_DAYS * SIM_SECONDS_PER_DAY) -> float | None:
        """Estimated total delta-v (m/s) for a there-and-back run.

        Used to pick missions a ship can actually finish, so the fleet grounds
        itself only when the network genuinely exceeds its budget.

        Solving a window means running a Lambert grid, which costs a few
        hundred milliseconds. Callers hit this every frame, so results are
        cached against simulation time and only refreshed once they are older
        than ``max_age``.
        """
        outbound, inbound = self.plan_round_trip(origin_key, target_key, max_age=max_age)
        if outbound is None or inbound is None:
            return None
        return self.delta_v_km_s(outbound.total_delta_v + inbound.total_delta_v) * 1000.0

    def affordable_targets(self, ship: Ship, margin: float = 1.15) -> list[tuple[str, float]]:
        """Trade targets whose round trip fits the ship's remaining propellant.

        Returns ``(target_key, round_trip_cost_ms)`` pairs, cheapest first.
        """
        affordable: list[tuple[str, float]] = []
        for key in TRADE_TARGETS:
            if key == ship.origin:
                continue
            cost = self.round_trip_cost_ms(ship.origin, key)
            if cost is not None and cost * margin <= ship.delta_v:
                affordable.append((key, cost))
        affordable.sort(key=lambda item: item[1])
        return affordable

    def refuel_docked_fleet(self, dt_days: float) -> float:
        """Regenerate propellant for freighters parked at the colony.

        Returns the m/s handed out so the caller can bill colony energy.
        """
        granted = 0.0
        for ship in self.ships:
            if ship.name in self.missions or ship.origin != "colony":
                continue
            headroom = SHIP_START_DELTA_V - ship.delta_v
            if headroom <= 0.0:
                continue
            amount = min(headroom, SHIP_REFUEL_RATE * dt_days)
            ship.delta_v += amount
            granted += amount
        return granted

    def cycle_warp(self, direction: int = 1) -> float:
        """Cycle the time warp through the configured steps."""
        steps = list(TIME_WARP_STEPS)
        if self.warp_days_per_second in steps:
            index = steps.index(self.warp_days_per_second)
            index = (index + direction) % len(steps)
        else:
            index = 0
        self.warp_days_per_second = float(steps[index])
        return self.warp_days_per_second

    # -- window solving ------------------------------------------------------
    def launch_window(self, origin_key: str, target_key: str, refresh: bool = False) -> window_solver.LaunchWindow | None:
        """Cheapest intercept opportunity between two bodies, memoised.

        A cached window may already be in the past. Callers that intend to
        fly it must pass ``not_before`` so the search is re-anchored: clamping
        a stale departure to "now" burns the ship onto a conic aimed at where
        the target used to be, which misses by tens of km/s.
        """
        cache_key = (origin_key, target_key)
        if not refresh and cache_key in self._window_cache:
            cached = self._window_cache[cache_key]
            if cached.departure_time >= self.time - 1e-9:
                return cached
        origin = self.bodies[origin_key]
        target = self.bodies[target_key]
        window = window_solver.solve_window(
            origin.elements, target.elements, MU_SUN,
            origin_key=origin_key, target_key=target_key,
            n_depart=WINDOW_GRID_DEPART, n_tof=WINDOW_GRID_TOF,
            epoch=self.time, min_departure_time=self.time,
        )
        if window is not None:
            self._window_cache[cache_key] = window
            self.stats["windows_solved"] += 1
        return window

    def porkchop(self, origin_key: str, target_key: str) -> dict:
        """Departure-time x time-of-flight delta-v grid, for plotting."""
        origin = self.bodies[origin_key]
        target = self.bodies[target_key]
        return window_solver.coarse_grid(
            origin.elements, target.elements, MU_SUN,
            n_depart=WINDOW_GRID_DEPART, n_tof=WINDOW_GRID_TOF,
        )

    def delta_v_km_s(self, value: float) -> float:
        """Convert a delta-v expressed in AU/year to km/s for display."""
        return value * AU_PER_YEAR_TO_KM_S

    # -- dispatch ------------------------------------------------------------
    def dispatch(self, ship: Ship, target_key: str, cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        """Send a parked ship on a supply run to ``target_key``."""
        if ship.name in self.missions:
            return False, f"{ship.name} is already flying a mission."
        if target_key not in self.bodies or target_key == ship.origin:
            return False, "Pick a destination other than the current one."

        window = self.launch_window(ship.origin, target_key)
        if window is None:
            return False, f"No intercept window found to {self.bodies[target_key].name}."

        # Price the mission on a freshly solved plan: the crew commits to
        # these burns, so the numbers must not come from a stale cache entry.
        outbound, return_window = self.plan_round_trip(ship.origin, target_key, max_age=None)
        if return_window is None:
            return False, f"No return window from {self.bodies[target_key].name} back home."
        dv_total = self.delta_v_km_s(outbound.total_delta_v + return_window.total_delta_v) * 1000.0
        if dv_total > ship.delta_v:
            return False, (
                f"Round trip needs {dv_total:.0f} m/s but {ship.name} has {ship.delta_v:.0f} m/s."
            )

        payload = cargo or self._default_payload(target_key, ship.capacity)
        load = sum(payload.values())
        if load > ship.capacity:
            return False, f"Cargo {load:.0f} t exceeds the {ship.capacity:.0f} t hold."

        self.missions[ship.name] = Mission(
            target=target_key,
            cargo=dict(payload),
            departure_time=window.departure_time,
            tof=window.tof,
            dv_depart=window.dv_depart,
            dv_arrive=window.dv_arrive,
            r_depart=window.r1.copy(),
            v_depart=window.v1.copy(),
            return_window=return_window,
            leg=Leg.PENDING,
        )
        ship.cargo = dict(payload)
        wait_days = (self.missions[ship.name].departure_time - self.time) / SIM_SECONDS_PER_DAY
        self.note(
            f"{ship.name} scheduled for {self.bodies[target_key].name} in {wait_days:.0f} d "
            f"(TOF {window.tof / SIM_SECONDS_PER_DAY:.0f} d, {dv_total:.0f} m/s total)."
        )
        return True, f"{ship.name} departs for {self.bodies[target_key].name} in {wait_days:.0f} days."

    def _default_payload(self, target_key: str, capacity: float) -> dict[str, float]:
        """Load the hold with whatever the destination's economy wants."""
        wanted = [r for r in ("iron", "components", "water", "ice") if r in ("iron", "components", "water", "ice")]
        if not wanted:
            return {"iron": capacity}
        share = capacity / len(wanted)
        return {key: share for key in wanted}

    # -- stepping ------------------------------------------------------------
    def _event_time(self, mission: Mission) -> float:
        """Absolute sim time at which the current leg of ``mission`` completes."""
        if mission.leg is Leg.PENDING:
            return mission.departure_time
        if mission.leg is Leg.WAITING:
            # The return conic is only valid at the window's own departure
            # instant, so the ship holds station until then.
            return mission.return_window.departure_time if mission.return_window else self.time
        return mission.departure_time + mission.tof

    def step(self, dt_days: float) -> list[LogEntry]:
        """Advance the simulation by ``dt_days`` and process mission events.

        Events are processed at their exact scheduled time rather than at
        whatever point the step happens to land on. That matters physically:
        the capture burn is ``|v_ship - v_body|`` evaluated at arrival, and
        letting the clock overshoot arrival by even a day moves both bodies
        enough to turn a 4 km/s match into a 30 km/s one.
        """
        before = len(self.log)
        target_time = self.time + dt_days * SIM_SECONDS_PER_DAY
        guard = 0

        while self.time < target_time and guard < 512:
            guard += 1
            due = None
            for ship in self.ships:
                mission = self.missions.get(ship.name)
                if mission is None:
                    continue
                when = self._event_time(mission)
                if when <= target_time and (due is None or when < due[1]):
                    due = (ship, when)
            if due is None:
                self.time = target_time
                break
            ship, when = due
            self.time = max(when, self.time)
            self._advance_mission(ship, self.missions[ship.name])

        # Freighters holding for a return window ride along with the body they
        # are parked on, so they are in the right place when it opens.
        for ship in self.ships:
            mission = self.missions.get(ship.name)
            if mission is not None and mission.leg is Leg.WAITING:
                ship.ride_with(self.bodies[mission.target], self.time)

        return self.log[before:]

    def _advance_mission(self, ship: Ship, mission: Mission) -> None:
        target = self.bodies[mission.target]
        if mission.leg is Leg.PENDING:
            self._depart(ship, mission)
        elif mission.leg is Leg.OUTBOUND:
            self._capture(ship, mission, target)
        elif mission.leg is Leg.WAITING:
            self._depart_home(ship, mission, target)
        elif mission.leg is Leg.INBOUND:
            self._complete_run(ship, mission)

    def _depart(self, ship: Ship, mission: Mission) -> None:
        """Burn onto the planned transfer conic at the scheduled instant.

        Only the departure burn is charged here; the arrival match burn is
        charged in ``_capture`` against the velocity the ship actually has,
        which is what makes the propellant budget a real constraint.
        """
        dv_burn = self.delta_v_km_s(mission.dv_depart) * 1000.0
        ship.anchor(self.time)
        ship.r = mission.r_depart.copy()
        ship.v = mission.v_depart.copy()
        ship.epoch = self.time
        ship.delta_v -= dv_burn
        self.stats["delta_v_spent"] += dv_burn
        mission.leg = Leg.OUTBOUND
        self.note(
            f"{ship.name} departed for {self.bodies[mission.target].name} "
            f"(TOF {mission.tof / SIM_SECONDS_PER_DAY:.0f} d, {dv_burn:.0f} m/s departure burn)."
        )

    def _capture(self, ship: Ship, mission: Mission, target: Body) -> None:
        """Match the target's velocity inside its SOI and unload."""
        r_target, v_target = window_solver.body_state(target.elements, MU_SUN, self.time)
        r_ship, v_ship = ship.state_at(self.time)
        dv_match = float(np.linalg.norm(v_ship - v_target))
        dv_match_ms = self.delta_v_km_s(dv_match) * 1000.0

        if dv_match_ms > ship.delta_v:
            # Not enough propellant to match: fly past and report the shortfall.
            self.note(
                f"{ship.name} could not match {target.name} "
                f"(needs {dv_match_ms:.0f} m/s, has {ship.delta_v:.0f} m/s). Cargo jettisoned."
            )
            ship.cargo = {}
            self.missions.pop(ship.name, None)
            return

        ship.delta_v -= dv_match_ms
        self.stats["delta_v_spent"] += dv_match_ms
        ship.r = r_target.copy()
        ship.v = v_target.copy()
        ship.epoch = self.time
        ship.origin = target.key
        mission.leg = Leg.CAPTURE

        delivered = float(sum(ship.cargo.values()))
        self.stats["mass_delivered"] += delivered
        self.pending_deliveries.append(
            Delivery(ship=ship.name, body=target.key, time=self.time, cargo=dict(ship.cargo))
        )
        self.note(
            f"{ship.name} captured at {target.name}: {delivered:.0f} t unloaded "
            f"({dv_match_ms:.0f} m/s match burn)."
        )
        ship.cargo = {}

        # Fly the return leg that was planned at dispatch time. Its departure
        # window was solved for this arrival epoch, so the burn is valid now.
        return_window = mission.return_window
        if return_window is None:
            self.note(f"{ship.name} is stranded at {target.name}: no return window.")
            self.missions.pop(ship.name, None)
            return

        dv_back = self.delta_v_km_s(return_window.total_delta_v) * 1000.0
        if dv_back > ship.delta_v:
            self.note(f"{ship.name} has only {ship.delta_v:.0f} m/s left; return needs {dv_back:.0f} m/s.")
            self.missions.pop(ship.name, None)
            return

        # No burn is charged here: the ship only *plans* the return leg and
        # holds station until the window opens. ``_depart_home`` charges the
        # departure burn and ``_complete_run`` charges the docking match, so
        # charging anything here would bill the same manoeuvre twice.
        mission.leg = Leg.WAITING
        mission.return_window = return_window
        self.stats["runs_completed"] += 1
        layover = (return_window.departure_time - self.time) / SIM_SECONDS_PER_DAY
        if layover > 0.5:
            self.note(
                f"{ship.name} holds at {target.name} for {layover:.0f} d until the return window opens."
            )
        else:
            self._depart_home(ship, mission, target)

    def _depart_home(self, ship: Ship, mission: Mission, target: Body) -> None:
        """Burn onto the return conic at the instant its window opens.

        The ship rides along with the target body while it waits, so it is
        exactly at the window's departure position when the burn happens.
        """
        return_window = mission.return_window
        # Charge only the departure burn here; the docking match burn is
        # charged in ``_complete_run``. Charging the window's *total* here
        # would bill the arrival burn twice and strand otherwise solvent ships.
        dv_back = self.delta_v_km_s(return_window.dv_depart) * 1000.0
        if dv_back > ship.delta_v:
            self.note(
                f"{ship.name} has only {ship.delta_v:.0f} m/s left; "
                f"return departure needs {dv_back:.0f} m/s."
            )
            self.missions.pop(ship.name, None)
            return

        ship.r = return_window.r1.copy()
        ship.v = return_window.v1.copy()
        ship.epoch = self.time
        ship.delta_v -= dv_back
        self.stats["delta_v_spent"] += dv_back
        mission.leg = Leg.INBOUND
        mission.departure_time = self.time
        mission.tof = return_window.tof
        self.note(
            f"{ship.name} departed {target.name} for Colony Hub "
            f"(TOF {return_window.tof / SIM_SECONDS_PER_DAY:.0f} d, {dv_back:.0f} m/s)."
        )

    def _complete_run(self, ship: Ship, mission: Mission) -> None:
        """Dock at the colony, charging the arrival match burn.

        Mirrors ``_capture``: arriving on a transfer conic means the ship is
        moving differently from the body it docks with, and matching that
        velocity costs propellant. Skipping it would make the return leg
        cheaper than the outbound one for no physical reason.
        """
        colony = self.bodies["colony"]
        r_colony, v_colony = window_solver.body_state(colony.elements, MU_SUN, self.time)
        _, v_ship = ship.state_at(self.time)
        dv_match_ms = self.delta_v_km_s(float(np.linalg.norm(v_ship - v_colony))) * 1000.0
        if dv_match_ms > ship.delta_v:
            self.note(
                f"{ship.name} reached Colony Hub but could not match orbit "
                f"(needs {dv_match_ms:.0f} m/s, has {ship.delta_v:.0f} m/s). Drifting."
            )
            self.missions.pop(ship.name, None)
            return
        ship.delta_v -= dv_match_ms
        self.stats["delta_v_spent"] += dv_match_ms
        ship.r = r_colony.copy()
        ship.v = v_colony.copy()
        ship.epoch = self.time
        ship.origin = "colony"
        self.missions.pop(ship.name, None)
        self.note(
            f"{ship.name} docked at Colony Hub ({dv_match_ms:.0f} m/s match). "
            f"Fleet delta-v left: {ship.delta_v:.0f} m/s."
        )

    # -- reporting -----------------------------------------------------------
    def ship_report(self, ship: Ship) -> dict:
        """Everything the HUD needs about one ship, in display units."""
        mission = self.missions.get(ship.name)
        r, v = ship.state_at(self.time)
        distance = float(np.linalg.norm(r))
        # While flying, the ship is bound for mission.target; otherwise it sits
        # wherever it was last anchored, which is not necessarily the colony --
        # a freighter abandoned short of return propellant stays put.
        at_key = mission.target if mission else ship.origin
        report = {
            "name": ship.name,
            "status": mission.leg.value if mission else Leg.PARKED.value,
            "at": self.bodies[at_key].name,
            "distance_au": distance,
            "speed_km_s": ship.speed_km_s,
            "delta_v_left": ship.delta_v,
            "cargo": float(sum(ship.cargo.values())),
            "eta_days": 0.0,
            "specific_energy": state_energy(r, v, MU_SUN),
            "at_key": at_key,
        }
        if mission is not None:
            report["eta_days"] = max(0.0, (mission.departure_time + mission.tof - self.time) / SIM_SECONDS_PER_DAY)
        return report

    def fleet_report(self) -> list[dict]:
        return [self.ship_report(ship) for ship in self.ships]
