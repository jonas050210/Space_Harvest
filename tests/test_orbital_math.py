"""Verification for the orbital-math layer.

These tests are the real check on ``src/maths``: rather than asserting that a
function returns *a* number, each one checks a physical invariant or an
independent closed-form result.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.maths import elements, kepler, transfers  # noqa: E402

MU_SUN = 1.32712440018e11  # km^3/s^2
AU = 1.495978707e8         # km


def circular_state(r: float, mu: float, inclination: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """A prograde circular state at radius ``r`` (optionally inclined)."""
    pos = np.array([r, 0.0, 0.0])
    v_circ = math.sqrt(mu / r)
    vel = np.array([0.0, v_circ * math.cos(inclination), v_circ * math.sin(inclination)])
    return pos, vel


# --------------------------------------------------------------------------
# Universal Kepler propagator
# --------------------------------------------------------------------------

def test_kepler_full_revolution_returns_to_start():
    """One full period must bring the state back to where it started."""
    r0, v0 = circular_state(AU, MU_SUN)
    el = elements.state_to_elements(r0, v0, MU_SUN)
    period = 2.0 * math.pi * math.sqrt(el.a ** 3 / MU_SUN)
    r, v = kepler.universal_kepler(r0, v0, period, MU_SUN)
    assert np.allclose(r, r0, rtol=1e-8, atol=1.0), f"position drift {np.linalg.norm(r - r0)} km"
    assert np.allclose(v, v0, rtol=1e-8, atol=1e-4)


@pytest.mark.parametrize("a_au,ecc", [(1.0, 0.0), (1.5, 0.21), (2.4, 0.55), (3.0, 0.85), (0.7, 0.9)])
def test_kepler_conserves_energy_and_angular_momentum(a_au, ecc):
    """Specific energy and h must be invariant under propagation."""
    a = a_au * AU
    rp = a * (1.0 - ecc)
    r0 = np.array([rp, 0.0, 0.0])
    v0 = np.array([0.0, math.sqrt(MU_SUN * (2.0 / rp - 1.0 / a)), 0.0])

    e0 = kepler.state_energy(r0, v0, MU_SUN)
    h0 = kepler.state_angular_momentum(r0, v0)
    r, v = kepler.universal_kepler(r0, v0, 4.0e7, MU_SUN)
    assert kepler.state_energy(r, v, MU_SUN) == pytest.approx(e0, rel=1e-10)
    assert np.allclose(kepler.state_angular_momentum(r, v), h0, rtol=1e-10)


def test_kepler_agrees_with_analytic_anomaly_propagation():
    """Cross-check the universal solver against mean-anomaly propagation."""
    r0, v0 = circular_state(1.5 * AU, MU_SUN)
    el = elements.state_to_elements(r0, v0, MU_SUN)
    dt = 3.0e6
    r_univ, _ = kepler.universal_kepler(r0, v0, dt, MU_SUN)

    el2 = elements.propagate_elements(el, MU_SUN, dt)
    r_elem, _ = elements.elements_to_state(el2, MU_SUN)
    assert np.allclose(r_univ, r_elem, rtol=1e-7)


def test_kepler_hyperbolic_escape():
    """A hyperbolic state should propagate outward and stay unbound."""
    r0 = np.array([AU, 0.0, 0.0])
    v_esc = math.sqrt(2.0 * MU_SUN / AU)
    v0 = np.array([0.0, v_esc * 1.2, 0.0])
    assert kepler.state_energy(r0, v0, MU_SUN) > 0.0
    r, v = kepler.universal_kepler(r0, v0, 1.0e8, MU_SUN)
    assert kepler.state_energy(r, v, MU_SUN) == pytest.approx(kepler.state_energy(r0, v0, MU_SUN), rel=1e-10)
    assert np.linalg.norm(r) > np.linalg.norm(r0)


def test_kepler_rejects_bad_input():
    r0, v0 = circular_state(AU, MU_SUN)
    with pytest.raises(ValueError):
        kepler.universal_kepler(np.zeros(3), v0, 100.0, MU_SUN)
    with pytest.raises(ValueError):
        kepler.universal_kepler(r0, v0, 100.0, 0.0)


# --------------------------------------------------------------------------
# Orbital elements
# --------------------------------------------------------------------------

def test_element_round_trip():
    """state -> elements -> state must be the identity."""
    rng = np.random.default_rng(7)
    for _ in range(25):
        r0, v0 = circular_state(rng.uniform(0.8, 3.2) * AU, MU_SUN, inclination=rng.uniform(0.0, 0.4))
        # Nudge into an eccentric, inclined orbit.
        v0 = v0 * rng.uniform(0.8, 1.15)
        v0[2] += rng.uniform(-4.0, 4.0)
        el = elements.state_to_elements(r0, v0, MU_SUN)
        r1, v1 = elements.elements_to_state(el, MU_SUN)
        assert np.allclose(r0, r1, rtol=1e-9, atol=1.0)
        assert np.allclose(v0, v1, rtol=1e-9, atol=1e-6)


def test_elements_match_vis_viva():
    """a from the elements must reproduce the vis-viva velocity."""
    r0, v0 = circular_state(2.0 * AU, MU_SUN)
    el = elements.state_to_elements(r0, v0, MU_SUN)
    assert el.a == pytest.approx(2.0 * AU, rel=1e-9)
    assert el.e == pytest.approx(0.0, abs=1e-9)
    v_visviva = math.sqrt(MU_SUN * (2.0 / np.linalg.norm(r0) - 1.0 / el.a))
    assert np.linalg.norm(v0) == pytest.approx(v_visviva, rel=1e-9)


def test_true_mean_anomaly_round_trip():
    for nu in np.linspace(0.0, 2.0 * math.pi, 13)[:-1]:
        m = elements.true_to_mean_anomaly(nu, 0.3)
        assert elements.mean_to_true_anomaly(m, 0.3) == pytest.approx(nu, abs=1e-9)


# --------------------------------------------------------------------------
# Hohmann reference
# --------------------------------------------------------------------------

def test_hohmann_matches_textbook_earth_to_mars():
    """Classic worked example: Earth orbit -> 1.524 AU, heliocentric.

    Published values for this transfer are ~2.94 km/s departure, ~2.65 km/s
    arrival and a ~259 day flight. Distances here are km and mu is km^3/s^2,
    so the solver must return km/s.
    """
    r1, r2 = AU, 1.524 * AU
    h = transfers.HohmannTransfer(r1, r2, MU_SUN)
    assert h.delta_v1 == pytest.approx(2.944, rel=0.005)
    assert h.delta_v2 == pytest.approx(2.646, rel=0.005)
    assert h.tof / 86400.0 == pytest.approx(259.0, rel=0.01)
    # The two burns are independent of direction for circular orbits.
    assert h.delta_v1 > 0.0 and h.delta_v2 > 0.0


def test_hohmann_delta_v_is_symmetric_in_direction():
    """Outbound and inbound Hohmann costs are equal for circular orbits."""
    h_out = transfers.HohmannTransfer(AU, 2.4 * AU, MU_SUN)
    h_in = transfers.HohmannTransfer(2.4 * AU, AU, MU_SUN)
    assert h_out.total_delta_v == pytest.approx(h_in.total_delta_v, rel=1e-9)


# --------------------------------------------------------------------------
# Lambert solver
# --------------------------------------------------------------------------

@pytest.mark.parametrize("a1,a2,inclination", [
    (1.0, 2.4, 0.0),
    (1.0, 2.4, 0.15),
    (2.4, 1.0, 0.0),
    (1.5, 3.2, 0.25),
])
def test_lambert_solution_actually_arrives(a1, a2, inclination):
    """Propagate the solved departure velocity and check the arrival position.

    This is the property that matters: the solver is only correct if the
    trajectory it returns really reaches the target at the stated time.
    """
    r1 = np.array([a1 * AU, 0.0, 0.0])
    # Target sits ahead on an inclined orbit.
    ang = math.radians(110.0)
    r2 = a2 * AU * np.array([math.cos(ang), math.sin(ang) * math.cos(inclination), math.sin(ang) * math.sin(inclination)])
    tof = 1.6e7

    v1, v2 = transfers.lambert(r1, r2, tof, MU_SUN)
    r_arr, v_arr = kepler.universal_kepler(r1, v1, tof, MU_SUN)
    miss = float(np.linalg.norm(r_arr - r2))
    assert miss < 1.0e-4 * np.linalg.norm(r2), f"miss distance {miss:.3e} km is too large"

    # The arrival velocity must match the solver's own claim.
    assert np.allclose(v_arr, v2, rtol=1e-6, atol=1e-3)


def test_lambert_recovers_hohmann_cost_for_coplanar_half_turn():
    """A near-180-degree coplanar transfer should cost close to the Hohmann value.

    Exactly 180 degrees makes r1 x r2 vanish, so the transfer plane is
    undefined; the test stands just off the axis where the geometry is
    well-posed but the delta-v is unchanged to within a fraction of a percent.
    """
    ang = math.radians(179.5)
    r1 = np.array([AU, 0.0, 0.0])
    r2 = 2.4 * AU * np.array([math.cos(ang), math.sin(ang), 0.0])
    h = transfers.HohmannTransfer(AU, 2.4 * AU, MU_SUN)
    v_circ1 = math.sqrt(MU_SUN / AU)
    v1, _ = transfers.lambert(r1, r2, h.tof, MU_SUN)
    # The Lambert burn is the same tangential prograde burn as Hohmann's first.
    assert np.linalg.norm(v1) == pytest.approx(v_circ1 + h.delta_v1, rel=1e-3)


def test_lambert_rejects_degenerate_geometry():
    r = np.array([AU, 0.0, 0.0])
    with pytest.raises(ValueError):
        transfers.lambert(r, r, 1.0e7, MU_SUN)          # identical points
    with pytest.raises(ValueError):
        transfers.lambert(r, r * -2.0, 0.0, MU_SUN)      # zero time of flight
    with pytest.raises(ValueError):
        transfers.lambert(np.zeros(3), r, 1.0e7, MU_SUN)  # zero radius


# --------------------------------------------------------------------------
# Multi-revolution Lambert (Izzo branches, M >= 1)
# --------------------------------------------------------------------------

def _half_turn_geometry():
    """A wide two-body geometry with a ~90-degree transfer angle."""
    r1 = np.array([1.2, 0.0, 0.0])
    r2 = np.array([0.0, 3.4, 0.3])
    c = float(np.linalg.norm(r2 - r1))
    s = 0.5 * (float(np.linalg.norm(r1)) + float(np.linalg.norm(r2)) + c)
    period = 2.0 * math.pi * math.sqrt(s ** 3 / MU_SUN)
    return r1, r2, s, period


def test_multi_rev_lambert_arrives_after_the_requested_revolutions():
    r1, r2, _s, period = _half_turn_geometry()
    tof = 1.6 * period
    solutions = transfers.lambert_multi(r1, r2, tof, MU_SUN, revs=1)
    assert len(solutions) == 2  # left and right branch of the TOF curve
    for v1, v2 in solutions:
        r_arr, _ = kepler.universal_kepler(r1, v1, tof, MU_SUN)
        assert r_arr == pytest.approx(r2, abs=1e-6)
        # Revolution count: the transfer orbit period must satisfy
        # M * P < tof < (M + 1) * P, i.e. the conic wraps once fully.
        a = 1.0 / (2.0 / float(np.linalg.norm(r1)) - float(np.dot(v1, v1)) / MU_SUN)
        orbital_period = 2.0 * math.pi * math.sqrt(a ** 3 / MU_SUN)
        assert 0.5 < orbital_period / tof < 1.0


def test_multi_rev_lambert_needs_a_long_enough_time_of_flight():
    r1, r2, _s, period = _half_turn_geometry()
    assert transfers.lambert_multi(r1, r2, 0.25 * period, MU_SUN, revs=1) == []
    assert transfers.lambert_multi(r1, r2, 0.05 * period, MU_SUN, revs=2) == []


def test_multi_rev_lambert_left_branch_is_cheaper_than_the_fast_single_rev():
    """The classical result this module exists for: at a long TOF the multi-rev
    conic is a lower-energy ride than the slow single-rev arc."""
    r1, r2, _s, period = _half_turn_geometry()
    tof = 1.6 * period
    single = transfers.lambert(r1, r2, tof, MU_SUN)
    multi = transfers.lambert_multi(r1, r2, tof, MU_SUN, revs=1)
    cost = lambda sol: float(np.linalg.norm(sol[0]) + np.linalg.norm(sol[1]))
    assert min(cost(s) for s in multi) < cost(single)
