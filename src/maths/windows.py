"""Launch-window search: when should a freighter leave, and what does it cost?

Two levels are provided:

``coarse_grid``
    Sweeps departure time x time-of-flight, solving Lambert at each node and
    scoring the total delta-v. This is what feeds the porkchop plot.

``solve_window``
    Takes the best coarse candidate and refines it so the ship really meets the
    moving target body. The refinement solves ``miss(tof) = 0`` by secant
    iteration, where ``miss`` is the distance between where the ship arrives
    and where the target actually is at arrival time. Without this step a
    Lambert transfer aims at a fixed point in space and sails past the target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .elements import OrbitalElements, elements_to_state, propagate_elements
from .kepler import universal_kepler
from .transfers import HohmannTransfer, lambert


@dataclass
class LaunchWindow:
    """A usable departure opportunity between two bodies."""

    departure_time: float   # simulation seconds since epoch
    tof: float              # time of flight, seconds
    dv_depart: float        # departure burn, m/s
    dv_arrive: float        # arrival circularisation / match burn, m/s
    target_key: str
    origin_key: str
    miss_distance: float    # residual after refinement (AU-scale units of caller)
    r1: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v1: np.ndarray = field(default_factory=lambda: np.zeros(3))
    r2: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v2: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v1_body: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v2_body: np.ndarray = field(default_factory=lambda: np.zeros(3))

    @property
    def total_delta_v(self) -> float:
        return self.dv_depart + self.dv_arrive

    @property
    def arrival_time(self) -> float:
        return self.departure_time + self.tof


def body_state(elements: OrbitalElements, mu: float, t: float) -> tuple[np.ndarray, np.ndarray]:
    """Heliocentric position and velocity of a body at time ``t``."""
    return elements_to_state(propagate_elements(elements, mu, t), mu)


def tof_grid_placeholder(n_tof: int, origin: OrbitalElements, target: OrbitalElements, mu: float) -> list[float]:
    """Time-of-flight axis used when a grid degenerates to zero departure rows."""
    tof_ref = HohmannTransfer(origin.a, target.a, mu).tof
    return list(np.linspace(0.45 * tof_ref, 2.6 * tof_ref, n_tof))


def synodic_period(el_a: OrbitalElements, el_b: OrbitalElements, mu: float) -> float:
    """Time between consecutive alignments of two bodies (seconds)."""
    n_a = math.sqrt(mu / el_a.a ** 3)
    n_b = math.sqrt(mu / el_b.a ** 3)
    dn = abs(n_a - n_b)
    if dn < 1.0e-15:
        return float("inf")
    return 2.0 * math.pi / dn


def _solve_to_target(origin: OrbitalElements, target: OrbitalElements, mu: float,
                     t_dep: float, tof: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float] | None:
    """Lambert-solve a transfer that actually intercepts the moving target.

    Returns ``(r1, v1, r2, v2, miss, tof)`` or ``None`` when no solution exists.
    The secant loop adjusts ``tof`` until the propagated arrival meets the
    target's propagated position.
    """
    r1, v1_body = body_state(origin, mu, t_dep)
    tof_cur, tof_prev = tof, tof * 1.12
    miss_prev = float("nan")
    for _ in range(24):
        r2, v2_body = body_state(target, mu, t_dep + tof_cur)
        try:
            v1, v2 = lambert(r1, r2, tof_cur, mu)
        except (ValueError, RuntimeError, ZeroDivisionError):
            return None
        r_arr, v_arr = universal_kepler(r1, v1, tof_cur, mu)
        miss = float(np.linalg.norm(r_arr - r2))
        if miss < 1.0e-7 * np.linalg.norm(r2):
            return r1, v1, r2, v2, miss, tof_cur
        # Secant step on tof, driven by how fast the miss distance is falling.
        if not math.isfinite(miss_prev) or abs(miss_prev - miss) < 1.0e-18:
            tof_prev, miss_prev = tof_cur, miss
            tof_cur *= 0.93
            continue
        tof_next = tof_cur - miss * (tof_cur - tof_prev) / (miss - miss_prev)
        if not math.isfinite(tof_next) or tof_next <= 0.0:
            tof_next = tof_cur * 0.93
        tof_prev, miss_prev = tof_cur, miss
        tof_cur = tof_next
        if abs(tof_cur - tof_prev) < 1.0e-9 * tof_cur:
            break
    return None


def coarse_grid(origin: OrbitalElements, target: OrbitalElements, mu: float,
                n_depart: int = 60, n_tof: int = 40,
                depart_span_years: float | None = None, epoch: float = 0.0,
                min_departure_time: float | None = None) -> dict:
    """Evaluate a departure-time x time-of-flight grid of delta-v costs.

    Returns a dictionary suitable for a porkchop plot:

    ``{"depart": [...], "tof": [...], "dv": ndarray (n_depart, n_tof), "best": LaunchWindow | None}``

    Departure times are absolute; ``epoch`` shifts the start of the sweep so a
    search begun mid-mission scans the upcoming synodic cycle rather than one
    anchored at t = 0. ``dv`` holds ``nan`` where no solution exists, so plots
    can mask it.
    """
    syn = synodic_period(origin, target, mu)
    year = 2.0 * math.pi * math.sqrt(1.0 ** 3 / mu)  # period of a 1-AU circular orbit
    span = (depart_span_years * year) if depart_span_years else max(syn, year)
    depart = list(np.linspace(epoch, epoch + span, n_depart))
    if min_departure_time is not None:
        # A departure before this instant is physically unreachable for the
        # caller (e.g. a return leg cannot leave before the ship has arrived),
        # so those columns are never even evaluated.
        depart = [t for t in depart if t >= min_departure_time - 1e-12]
        if not depart:
            return {"depart": [], "tof": tof_grid_placeholder(n_tof, origin, target, mu),
                    "dv": np.zeros((0, n_tof)), "best": None}

    # Time-of-flight candidates bracketed around the Hohmann half-period.
    tof_ref = HohmannTransfer(origin.a, target.a, mu).tof
    tof_grid = list(np.linspace(0.45 * tof_ref, 2.6 * tof_ref, n_tof))

    dv = np.full((len(depart), len(tof_grid)), np.nan)
    best: LaunchWindow | None = None

    for i, t_dep in enumerate(depart):
        r1, v1_body = body_state(origin, mu, t_dep)
        for j, tof in enumerate(tof_grid):
            r2, v2_body = body_state(target, mu, t_dep + tof)
            try:
                v1, v2 = lambert(r1, r2, tof, mu)
            except (ValueError, RuntimeError, ZeroDivisionError):
                continue
            dv_total = float(np.linalg.norm(v1 - v1_body) + np.linalg.norm(v2 - v2_body))
            dv[i, j] = dv_total
            if best is None or dv_total < best.total_delta_v:
                best = LaunchWindow(
                    departure_time=t_dep, tof=tof,
                    dv_depart=float(np.linalg.norm(v1 - v1_body)),
                    dv_arrive=float(np.linalg.norm(v2 - v2_body)),
                    target_key="", origin_key="",
                    miss_distance=float("nan"),
                    r1=r1, v1=v1, r2=r2, v2=v2, v1_body=v1_body, v2_body=v2_body,
                )
    return {"depart": depart, "tof": tof_grid, "dv": dv, "best": best}


def solve_window(origin: OrbitalElements, target: OrbitalElements, mu: float,
                 origin_key: str = "", target_key: str = "",
                 n_depart: int = 48, n_tof: int = 24,
                 depart_span_years: float | None = None,
                 max_departure_time: float | None = None,
                 min_departure_time: float | None = None,
                 epoch: float = 0.0) -> LaunchWindow | None:
    """Find the cheapest genuine intercept opportunity, refined to a real rendezvous.

    ``max_departure_time`` lets the caller restrict the search to windows that
    open within a mission horizon.
    """
    grid = coarse_grid(origin, target, mu, n_depart=n_depart, n_tof=n_tof,
                       depart_span_years=depart_span_years, epoch=epoch,
                       min_departure_time=min_departure_time)
    candidates: list[tuple[float, float, float]] = []
    for i, t_dep in enumerate(grid["depart"]):
        if max_departure_time is not None and t_dep > max_departure_time:
            continue
        if min_departure_time is not None and t_dep < min_departure_time - 1e-12:
            continue
        for j, tof in enumerate(grid["tof"]):
            value = grid["dv"][i, j]
            if math.isnan(value):
                continue
            candidates.append((float(value), float(t_dep), float(tof)))
    if not candidates:
        return None
    candidates.sort()

    # Refine the cheapest handful; the coarse winner is not always feasible.
    for _, t_dep, tof in candidates[:6]:
        solved = _solve_to_target(origin, target, mu, t_dep, tof)
        if solved is None:
            continue
        r1, v1, r2, v2, miss, tof_solved = solved
        v1_body = body_state(origin, mu, t_dep)[1]
        v2_body = body_state(target, mu, t_dep + tof_solved)[1]
        return LaunchWindow(
            departure_time=t_dep, tof=tof_solved,
            dv_depart=float(np.linalg.norm(v1 - v1_body)),
            dv_arrive=float(np.linalg.norm(v2 - v2_body)),
            origin_key=origin_key, target_key=target_key,
            miss_distance=miss, r1=r1, v1=v1, r2=r2, v2=v2,
            v1_body=v1_body, v2_body=v2_body,
        )
    return None
