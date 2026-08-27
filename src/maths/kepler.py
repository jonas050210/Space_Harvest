"""Universal-variable Kepler propagation.

Given a state ``r, v`` and a gravitational parameter ``mu``, advance the state
by ``dt`` without numerical integration error. The formulation below is the
standard universal-variable / Stumpff-function approach (Bate, Mueller &
White; Vallado ch. 3.7), which handles elliptical, parabolic and hyperbolic
orbits with one code path.

Units are whatever the caller chooses, as long as ``mu`` matches. The
simulation layer uses kilometres and seconds.
"""

from __future__ import annotations

import numpy as np

# Convergence settings for the universal Kepler solver.
_NEWTON_MAX_ITER = 120
# The universal anomaly chi has units of sqrt(length), so for heliocentric
# distances it is ~1e5 and a Newton step only becomes tiny relative to it.
# The test is therefore relative, with an absolute floor for tiny orbits.
_REL_TOL = 1.0e-14
_ABS_TOL = 1.0e-9


def _stumpff(psi: float) -> tuple[float, float]:
    """Return the Stumpff functions ``c2`` and ``c3`` for argument ``psi``.

    ``psi > 0`` is elliptical, ``psi < 0`` hyperbolic and ``psi == 0``
    parabolic; the series forms are used near zero to avoid the ``0/0`` limit.
    """
    if psi > 1.0e-6:
        root = np.sqrt(psi)
        return (1.0 - np.cos(root)) / psi, (root - np.sin(root)) / (root ** 3)
    if psi < -1.0e-6:
        root = np.sqrt(-psi)
        return (1.0 - np.cosh(root)) / psi, (np.sinh(root) - root) / (root ** 3)
    # Series expansion around psi = 0 (parabolic limit).
    return 0.5 - psi / 24.0 + psi ** 2 / 720.0, 1.0 / 6.0 - psi / 120.0 + psi ** 2 / 5040.0


def universal_kepler(r0: np.ndarray, v0: np.ndarray, dt: float, mu: float) -> tuple[np.ndarray, np.ndarray]:
    """Propagate ``r0, v0`` by ``dt`` seconds under two-body motion.

    Returns ``(r, v)`` as float numpy arrays. Raises ``ValueError`` for
    degenerate input (zero radius, non-positive mu) or if the universal
    anomaly solver fails to converge.
    """
    r0 = np.asarray(r0, dtype=float)
    v0 = np.asarray(v0, dtype=float)
    if mu <= 0.0:
        raise ValueError("mu must be positive")

    r0_norm = float(np.linalg.norm(r0))
    if r0_norm == 0.0:
        raise ValueError("radius vector has zero length")

    v0_norm = float(np.linalg.norm(v0))
    rdotv = float(np.dot(r0, v0))
    alpha = (2.0 / r0_norm) - (v0_norm ** 2 / mu)  # 1/a; sign encodes orbit type.
    sqrt_mu = np.sqrt(mu)

    # The universal Kepler equation is monotone in chi only across a single
    # revolution, so whole revolutions are folded out first and the solver
    # only ever sees a remainder in [0, T). Propagating by an exact period is
    # the identity, so this is exact rather than an approximation.
    a = 1.0 / alpha if abs(alpha) > 1.0e-14 else float("inf")
    if a > 0.0 and np.isfinite(a):
        period = 2.0 * np.pi * np.sqrt(a ** 3 / mu)
        dt -= int(np.floor(dt / period)) * period

    # Bracket the root. f(0) = -sqrt(mu)*dt and f is monotone increasing in
    # chi across one revolution, so a forward step roots in [0, chi_rev].
    chi_rev = 2.0 * np.pi * np.sqrt(a) if (a > 0.0 and np.isfinite(a)) else float("inf")
    if dt >= 0.0:
        lo, hi = 0.0, chi_rev
    else:
        lo, hi = -chi_rev, 0.0

    # Closed-form initial guesses (Bate, Mueller & White 4.5), each guarded so
    # a degenerate value can never poison the iteration.
    chi = None
    if 0.0 < a < float("inf"):  # ellipse
        chi = np.sqrt(mu / a ** 3) * dt
    elif a < 0.0:  # hyperbola
        denom = rdotv + np.sign(dt) * np.sqrt(-mu * a) * (1.0 - r0_norm * alpha)
        numer = -2.0 * mu * alpha * dt
        if denom > 0.0 and numer > 0.0:
            chi = np.sign(dt) * np.sqrt(-a) * np.log(numer / denom)
    if chi is None or not np.isfinite(chi):  # parabola, or a failed guess
        chi = sqrt_mu * dt / r0_norm
    # Never start outside the bracket.
    if not (lo <= chi <= hi):
        chi = 0.5 * (lo + hi) if np.isfinite(lo) and np.isfinite(hi) else max(chi, 0.0)

    psi = alpha * chi ** 2
    for _ in range(_NEWTON_MAX_ITER):
        psi = alpha * chi ** 2
        c2, c3 = _stumpff(psi)
        f_norm = (
            rdotv / sqrt_mu * chi ** 2 * c2
            + (1.0 - alpha * r0_norm) * chi ** 3 * c3
            + r0_norm * chi
            - sqrt_mu * dt
        )
        # df/dchi is exactly the radius at chi (Vallado Alg. 1), which is
        # strictly positive, so f is monotone increasing and the sign of f
        # tells us which half of the bracket the root lives in.
        fp_norm = (
            chi ** 2 * c2
            + rdotv / sqrt_mu * chi * (1.0 - psi * c3)
            + r0_norm * (1.0 - psi * c2)
        )
        if f_norm > 0.0:
            hi = min(hi, chi)
        else:
            lo = max(lo, chi)

        delta = f_norm / fp_norm if abs(fp_norm) > 1.0e-300 else float("inf")
        chi_next = chi - delta
        if not np.isfinite(chi_next) or not (lo <= chi_next <= hi):
            chi_next = 0.5 * (lo + hi)  # bisection repair inside the bracket
        converged = abs(chi_next - chi) <= _REL_TOL * max(abs(chi_next), _ABS_TOL)
        chi = chi_next
        if converged:
            break
    else:
        raise ValueError("universal Kepler solver did not converge")

    psi = alpha * chi ** 2
    c2, c3 = _stumpff(psi)
    r_norm = chi ** 2 * c2 + rdotv / sqrt_mu * chi * (1.0 - psi * c3) + r0_norm * (1.0 - psi * c2)

    f = 1.0 - chi ** 2 * c2 / r0_norm
    g = dt - chi ** 3 * c3 / sqrt_mu
    f_dot = sqrt_mu / (r_norm * r0_norm) * chi * (psi * c3 - 1.0)
    g_dot = 1.0 - chi ** 2 * c2 / r_norm

    return f * r0 + g * v0, f_dot * r0 + g_dot * v0


def state_energy(r: np.ndarray, v: np.ndarray, mu: float) -> float:
    """Specific orbital energy ``epsilon = v^2/2 - mu/r`` (conserved)."""
    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)
    return 0.5 * float(np.dot(v, v)) - mu / float(np.linalg.norm(r))


def state_angular_momentum(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Specific angular momentum vector ``h = r x v`` (conserved)."""
    return np.cross(np.asarray(r, dtype=float), np.asarray(v, dtype=float))


def period(r: np.ndarray, v: np.ndarray, mu: float) -> float | None:
    """Orbital period in seconds, or ``None`` for unbound trajectories."""
    energy = state_energy(r, v, mu)
    if energy >= 0.0:
        return None
    a = -mu / (2.0 * energy)
    return 2.0 * np.pi * np.sqrt(a ** 3 / mu)
