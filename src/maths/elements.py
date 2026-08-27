"""Conversions between Cartesian state vectors and classical orbital elements.

Only what the prototype needs: ``a, e, i, raan, argp, nu`` (and true anomaly
derived quantities). Round-trip fidelity is asserted in the test-suite.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .kepler import state_angular_momentum

_TINY = 1.0e-14


@dataclass(frozen=True)
class OrbitalElements:
    """Classical Keplerian elements, angles in radians."""

    a: float      # semi-major axis (same length unit as input state)
    e: float      # eccentricity
    i: float      # inclination
    raan: float   # right ascension of ascending node
    argp: float   # argument of periapsis
    nu: float     # true anomaly

    @property
    def period(self) -> float:
        """Orbital period in seconds for the mu used to build these elements."""
        raise NotImplementedError

    def radius(self) -> float:
        """Current orbital radius ``r = a(1-e^2)/(1+e cos nu)``."""
        return self.a * (1.0 - self.e ** 2) / (1.0 + self.e * np.cos(self.nu))


def state_to_elements(r: np.ndarray, v: np.ndarray, mu: float) -> OrbitalElements:
    """Convert a Cartesian state into classical orbital elements."""
    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)

    r_norm = float(np.linalg.norm(r))
    v_norm = float(np.linalg.norm(v))
    energy = 0.5 * v_norm ** 2 - mu / r_norm

    h = state_angular_momentum(r, v)
    h_norm = float(np.linalg.norm(h))
    if h_norm < _TINY:
        raise ValueError("rectilinear orbit: orbital elements are undefined")

    n_hat = np.array([-h[1], h[0], 0.0])
    n_norm = float(np.linalg.norm(n_hat))

    e_vec = ((v_norm ** 2 - mu / r_norm) * r - float(np.dot(r, v)) * v) / mu
    e = float(np.linalg.norm(e_vec))

    if abs(energy) < _TINY:
        a = float("inf")
    else:
        a = -mu / (2.0 * energy)

    i = float(np.arccos(np.clip(h[2] / h_norm, -1.0, 1.0)))

    if n_norm > _TINY:
        raan = float(np.arccos(np.clip(n_hat[0] / n_norm, -1.0, 1.0)))
        if n_hat[1] < 0.0:
            raan = 2.0 * np.pi - raan
    else:
        raan = 0.0

    if e > _TINY and n_norm > _TINY:
        argp = float(np.arccos(np.clip(float(np.dot(n_hat, e_vec)) / (n_norm * e), -1.0, 1.0)))
        if e_vec[2] < 0.0:
            argp = 2.0 * np.pi - argp
    else:
        argp = 0.0

    if e > _TINY:
        nu = float(np.arccos(np.clip(float(np.dot(e_vec, r)) / (e * r_norm), -1.0, 1.0)))
        if float(np.dot(r, v)) < 0.0:
            nu = 2.0 * np.pi - nu
    else:  # circular orbit: measure true anomaly from the node instead.
        if n_norm > _TINY:
            nu = float(np.arccos(np.clip(float(np.dot(n_hat, r)) / (n_norm * r_norm), -1.0, 1.0)))
            if r[2] < 0.0:
                nu = 2.0 * np.pi - nu
        else:
            nu = 0.0

    return OrbitalElements(a=a, e=e, i=i, raan=raan, argp=argp, nu=nu)


def elements_to_state(el: OrbitalElements, mu: float) -> tuple[np.ndarray, np.ndarray]:
    """Convert classical orbital elements back into a Cartesian state."""
    a, e, i, raan, argp, nu = el.a, el.e, el.i, el.raan, el.argp, el.nu
    p = a * (1.0 - e ** 2)
    r_mag = p / (1.0 + e * np.cos(nu))

    # Position and velocity in the perifocal (PQW) frame.
    r_pqw = np.array([r_mag * np.cos(nu), r_mag * np.sin(nu), 0.0])
    sqrt_mu_p = np.sqrt(mu / p)
    v_pqw = sqrt_mu_p * np.array([-np.sin(nu), e + np.cos(nu), 0.0])

    # Rotation from perifocal to the inertial frame.
    co, so = np.cos(raan), np.sin(raan)
    cw, sw = np.cos(argp), np.sin(argp)
    ci, si = np.cos(i), np.sin(i)
    rot = np.array(
        [
            [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
            [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
            [sw * si, cw * si, ci],
        ]
    )
    return rot @ r_pqw, rot @ v_pqw


def true_to_mean_anomaly(nu: float, e: float) -> float:
    """True anomaly -> mean anomaly, normalised to ``[0, 2 pi)``."""
    ecc = np.arctan2(np.sqrt(1.0 - e ** 2) * np.sin(nu), e + np.cos(nu))
    m = ecc - e * np.sin(ecc)
    return float(np.mod(m, 2.0 * np.pi))


def mean_to_true_anomaly(m: float, e: float) -> float:
    """Mean anomaly -> true anomaly, normalised to ``[0, 2 pi)``.

    Newton's method on Kepler's equation with a Danby-style starting guess,
    which stays well behaved up to moderately high eccentricity.
    """
    m = float(np.mod(m, 2.0 * np.pi))
    ecc = m + 0.85 * e * np.sign(np.sin(m))
    for _ in range(80):
        f = ecc - e * np.sin(ecc) - m
        fp = 1.0 - e * np.cos(ecc)
        if abs(fp) < 1.0e-12:
            break
        delta = f / fp
        ecc -= delta
        if abs(delta) < 1.0e-13:
            break
    nu = np.arctan2(np.sqrt(1.0 - e ** 2) * np.sin(ecc), np.cos(ecc) - e)
    return float(np.mod(nu, 2.0 * np.pi))


def propagate_elements(el: OrbitalElements, mu: float, dt: float) -> OrbitalElements:
    """Advance elements forward in time (only mean anomaly changes)."""
    n = np.sqrt(mu / el.a ** 3)
    m = true_to_mean_anomaly(el.nu, el.e) + n * dt
    return OrbitalElements(a=el.a, e=el.e, i=el.i, raan=el.raan, argp=el.argp, nu=mean_to_true_anomaly(m, el.e))
