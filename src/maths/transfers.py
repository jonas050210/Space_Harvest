"""Two-impulse transfer solutions: Hohmann plus a universal Lambert solver.

The Lambert solver is the single-revolution branch of Dario Izzo's universal
algorithm ("Revisiting Lambert's problem", Celestial Mechanics and Dynamical
Astronomy, 2015), transcribed here in plain numpy so the prototype has no
dependency beyond numpy itself. Transcription follows the reference
implementation by Juan Luis Cano Rodriguez and the poliastro team (MIT
licensed), adapted by removing the numba JIT layer.

Everything is verified in ``tests/test_orbital_math.py`` by propagating the
returned departure velocity with the universal Kepler propagator and checking
that it actually arrives at the requested position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HohmannTransfer:
    """Coplanar, tangent two-impulse transfer between two circular orbits.

    All velocities come out in ``length-unit / second`` for whatever length
    unit ``r1``, ``r2`` and ``mu`` were supplied in, so a call in km gives
    km/s. This is the reference against which the numerically searched launch
    windows are sanity-checked: an in-plane transfer between circular orbits
    should never be much cheaper than the Hohmann cost.
    """

    r1: float
    r2: float
    mu: float

    @property
    def a_transfer(self) -> float:
        return 0.5 * (self.r1 + self.r2)

    @property
    def delta_v1(self) -> float:
        v_circ1 = math.sqrt(self.mu / self.r1)
        v_peri = math.sqrt(self.mu * (2.0 / self.r1 - 1.0 / self.a_transfer))
        return abs(v_peri - v_circ1)

    @property
    def delta_v2(self) -> float:
        v_circ2 = math.sqrt(self.mu / self.r2)
        v_apo = math.sqrt(self.mu * (2.0 / self.r2 - 1.0 / self.a_transfer))
        return abs(v_circ2 - v_apo)

    @property
    def total_delta_v(self) -> float:
        return self.delta_v1 + self.delta_v2

    @property
    def tof(self) -> float:
        """Time of flight in seconds: half the transfer-ellipse period."""
        return math.pi * math.sqrt(self.a_transfer ** 3 / self.mu)

    @property
    def phase_angle(self) -> float:
        """Ideal angular separation of the target body at departure (radians)."""
        omega_target = math.sqrt(self.mu / self.r2 ** 3)
        return math.pi - omega_target * self.tof


# --------------------------------------------------------------------------
# Izzo (2015) universal Lambert solver, single revolution
# --------------------------------------------------------------------------

def _hyp2f1b(x: float) -> float:
    """Hypergeometric 2F1(3, 1, 5/2, x) via its series expansion (Battin)."""
    if x >= 1.0:
        return float("inf")
    res = 1.0
    term = 1.0
    i = 0
    while True:
        term = term * (3 + i) * (1 + i) / (2.5 + i) * x / (i + 1)
        old = res
        res += term
        if old == res:
            return res
        i += 1


def _compute_y(x: float, lam: float) -> float:
    return math.sqrt(max(0.0, 1.0 - lam ** 2 * (1.0 - x ** 2)))


def _compute_psi(x: float, y: float, lam: float) -> float:
    """Auxiliary angle psi, Izzo Eq. (17)."""
    if -1.0 <= x < 1.0:  # ellipse
        return math.acos(max(-1.0, min(1.0, x * y + lam * (1.0 - x ** 2))))
    if x > 1.0:  # hyperbola
        return math.asinh((y - x * lam) * math.sqrt(x ** 2 - 1.0))
    return 0.0  # parabola


def _tof_equation(x: float, t0: float, lam: float, revs: int = 0) -> float:
    y = _compute_y(x, lam)
    if revs == 0 and math.sqrt(0.6) < x < math.sqrt(1.4):
        eta = y - lam * x
        s1 = (1.0 - lam - x * eta) * 0.5
        q = 4.0 / 3.0 * _hyp2f1b(s1)
        t = (eta ** 3 * q + 4.0 * lam * eta) * 0.5
    else:
        psi = _compute_psi(x, y, lam)
        t = ((psi + revs * math.pi) / math.sqrt(abs(1.0 - x ** 2)) - x + lam * y) / (1.0 - x ** 2)
    return t - t0


def _tof_eq_p(x: float, y: float, t: float, lam: float) -> float:
    return (3.0 * t * x - 2.0 + 2.0 * lam ** 3 * x / y) / (1.0 - x ** 2)


def _tof_eq_p2(x: float, y: float, t: float, dt: float, lam: float) -> float:
    return (3.0 * t + 5.0 * x * dt + 2.0 * (1.0 - lam ** 2) * lam ** 3 / y ** 3) / (1.0 - x ** 2)


def _tof_eq_p3(x: float, y: float, dt: float, dd_t: float, lam: float) -> float:
    return (7.0 * x * dd_t + 8.0 * dt - 6.0 * (1.0 - lam ** 2) * lam ** 5 * x / y ** 5) / (1.0 - x ** 2)


def _initial_guess(t: float, lam: float) -> float:
    """Izzo Eq. (19)/(21) plus the corrected piecewise middle branch."""
    t0 = math.acos(lam) + lam * math.sqrt(1.0 - lam ** 2)
    t1 = 2.0 * (1.0 - lam ** 3) / 3.0
    if t >= t0:
        return (t0 / t) ** (2.0 / 3.0) - 1.0
    if t < t1:
        return 2.5 * t1 / t * (t1 - t) / (1.0 - lam ** 5) + 1.0
    return math.exp(math.log(2.0) * math.log(t / t0) / math.log(t1 / t0)) - 1.0


def _householder(x0: float, t0: float, lam: float, maxiter: int = 35, atol: float = 1.0e-8, rtol: float = 1.0e-10) -> float:
    """Quartic Householder iteration for a zero of the time-of-flight equation."""
    x = x0
    for _ in range(maxiter):
        y = _compute_y(x, lam)
        fval = _tof_equation(x, t0, lam)
        t = fval + t0
        fder = _tof_eq_p(x, y, t, lam)
        fder2 = _tof_eq_p2(x, y, t, fder, lam)
        fder3 = _tof_eq_p3(x, y, fder, fder2, lam)
        denom = fder * (fder ** 2 - fval * fder2) + fder3 * fval ** 2 / 6.0
        if denom == 0.0:
            raise RuntimeError("Lambert Householder step hit a zero denominator")
        nxt = x - fval * ((fder ** 2 - fval * fder2 / 2.0) / denom)
        if abs(nxt - x) < rtol * abs(x) + atol:
            return nxt
        x = nxt
    raise RuntimeError("Lambert solver failed to converge")


def lambert(r1: np.ndarray, r2: np.ndarray, tof: float, mu: float, prograde: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Solve the single-revolution Lambert problem.

    Returns ``(v1, v2)``: the departure and arrival velocity vectors. Raise
    ``ValueError`` for degenerate geometry (zero time of flight, or collinear
    position vectors where the transfer plane is undefined).
    """
    r1 = np.asarray(r1, dtype=float)
    r2 = np.asarray(r2, dtype=float)
    if tof <= 0.0:
        raise ValueError("time of flight must be positive")
    if mu <= 0.0:
        raise ValueError("mu must be positive")

    chord = r2 - r1
    c_norm = float(np.linalg.norm(chord))
    r1_norm = float(np.linalg.norm(r1))
    r2_norm = float(np.linalg.norm(r2))
    if r1_norm == 0.0 or r2_norm == 0.0 or c_norm == 0.0:
        raise ValueError("degenerate Lambert geometry")

    s = (r1_norm + r2_norm + c_norm) * 0.5  # semiperimeter
    i_r1, i_r2 = r1 / r1_norm, r2 / r2_norm
    i_h = np.cross(i_r1, i_r2)
    h_norm = float(np.linalg.norm(i_h))
    if h_norm < 1.0e-12:
        raise ValueError("collinear position vectors: transfer plane undefined")
    i_h = i_h / h_norm

    lam = math.sqrt(max(0.0, min(1.0, 1.0 - c_norm / s)))

    # Tangential unit vectors depend on which way the transfer plane is tilted.
    if i_h[2] < 0.0:
        lam = -lam
        i_t1, i_t2 = np.cross(i_r1, i_h), np.cross(i_r2, i_h)
    else:
        i_t1, i_t2 = np.cross(i_h, i_r1), np.cross(i_h, i_r2)

    if not prograde:
        lam, i_t1, i_t2 = -lam, -i_t1, -i_t2

    t_nondim = math.sqrt(2.0 * mu / s ** 3) * tof
    x = _householder(_initial_guess(t_nondim, lam), t_nondim, lam)
    y = _compute_y(x, lam)

    gamma = math.sqrt(mu * s / 2.0)
    rho = (r1_norm - r2_norm) / c_norm
    sigma = math.sqrt(max(0.0, 1.0 - rho ** 2))

    v_r1 = gamma * ((lam * y - x) - rho * (lam * y + x)) / r1_norm
    v_r2 = -gamma * ((lam * y - x) + rho * (lam * y + x)) / r2_norm
    v_t1 = gamma * sigma * (y + lam * x) / r1_norm
    v_t2 = gamma * sigma * (y + lam * x) / r2_norm

    v1 = v_r1 * i_r1 + v_t1 * i_t1
    v2 = v_r2 * i_r2 + v_t2 * i_t2
    return v1, v2
