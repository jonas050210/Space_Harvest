"""Verification for the supply-chain simulation and the body network.

These exercise the real code path used by the game: ``OrbitalSimulation``
is stepped the same way ``src/main.py`` steps it, so a regression in burn
accounting, event timing or window solving shows up here rather than only
in a window the developer has to stare at.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import (  # noqa: E402
    AU_PER_YEAR_TO_KM_S,
    MU_SUN,
    SHIP_START_DELTA_V,
    SIM_SECONDS_PER_DAY,
    SIM_SECONDS_PER_YEAR,
)
from src.maths import windows as window_solver  # noqa: E402
from src.maths.transfers import HohmannTransfer  # noqa: E402
from src.simulation.bodies import BODIES, TRADE_TARGETS, orbital_speed_km_s, orbit_points  # noqa: E402
from src.simulation.orbital_sim import Leg, OrbitalSimulation  # noqa: E402


def run_until_idle(sim: OrbitalSimulation, dt_days: float = 3.0, max_steps: int = 8000) -> None:
    for _ in range(max_steps):
        sim.step(dt_days)
        if not sim.missions:
            return


# --------------------------------------------------------------------------
# Unit conventions
# --------------------------------------------------------------------------

def test_au_per_year_converts_to_earth_orbital_speed():
    """The single easiest thing to get wrong in this codebase.

    With mu = 4 pi^2 and lengths in AU, sqrt(mu / 1 AU) = 2 pi is one AU per
    year, which is Earth's mean orbital speed: 29.78 km/s.
    """
    speed = math.sqrt(MU_SUN / 1.0) * AU_PER_YEAR_TO_KM_S
    assert speed == pytest.approx(29.78, rel=0.005)


def test_body_orbital_speeds_follow_kepler():
    """v scales as 1/sqrt(a); Earth's speed is the anchor."""
    for key in TRADE_TARGETS:
        a = BODIES[key].elements.a
        expected = 29.78 / math.sqrt(a)
        assert orbital_speed_km_s(key) == pytest.approx(expected, rel=0.01)


def test_sim_year_and_day_are_consistent():
    assert SIM_SECONDS_PER_YEAR / SIM_SECONDS_PER_DAY == pytest.approx(365.25, rel=1e-9)


def test_orbit_points_are_closed_and_at_the_right_radius():
    pts = orbit_points("metallic_belt", samples=128)
    assert pts.shape == (129, 3)
    radii = np.linalg.norm(pts, axis=1)
    el = BODIES["metallic_belt"].elements
    r_peri, r_apo = el.a * (1 - el.e), el.a * (1 + el.e)
    # Every sample lies between periapsis and apoapsis...
    assert radii.min() >= r_peri - 1e-12
    assert radii.max() <= r_apo + 1e-12
    # ...and a 128-point sweep of true anomaly gets close to both apses.
    assert radii.min() == pytest.approx(r_peri, rel=1e-4)
    assert radii.max() == pytest.approx(r_apo, rel=1e-4)
    # Closed curve: first and last sample coincide.
    assert np.allclose(pts[0], pts[-1], rtol=1e-12, atol=1e-12)


# --------------------------------------------------------------------------
# Window solving
# --------------------------------------------------------------------------

def test_best_window_beats_or_matches_hohmann_reference():
    """A searched window should never be much worse than the Hohmann ideal."""
    for target in TRADE_TARGETS:
        window = window_solver.solve_window(
            BODIES["colony"].elements, BODIES[target].elements, MU_SUN,
            origin_key="colony", target_key=target,
        )
        assert window is not None, f"no window to {target}"
        hohmann = HohmannTransfer(BODIES["colony"].elements.a, BODIES[target].elements.a, MU_SUN)
        best = window.total_delta_v * AU_PER_YEAR_TO_KM_S * 1000.0
        ideal = hohmann.total_delta_v * AU_PER_YEAR_TO_KM_S * 1000.0
        # Inclined, eccentric targets cost more than the coplanar circular
        # ideal, but not by an unreasonable factor.
        assert best <= ideal * 1.20, f"{target}: {best:.0f} m/s vs Hohmann {ideal:.0f} m/s"


def test_window_actually_intercepts_the_moving_target():
    """The refinement must drive the miss distance to ~zero."""
    for target in TRADE_TARGETS:
        window = window_solver.solve_window(
            BODIES["colony"].elements, BODIES[target].elements, MU_SUN,
        )
        assert window.miss_distance < 1.0e-8, f"{target}: miss {window.miss_distance:.2e} AU"


def test_window_search_respects_the_epoch_offset():
    """A search anchored mid-mission must return departures after that epoch."""
    epoch = 1.5 * SIM_SECONDS_PER_YEAR
    window = window_solver.solve_window(
        BODIES["colony"].elements, BODIES["metallic_belt"].elements, MU_SUN,
        epoch=epoch,
    )
    assert window is not None
    assert window.departure_time >= epoch - 1e-9


def test_porkchop_grid_shape_and_finite_costs():
    grid = window_solver.coarse_grid(
        BODIES["colony"].elements, BODIES["metallic_belt"].elements, MU_SUN,
        n_depart=24, n_tof=16,
    )
    assert grid["dv"].shape == (24, 16)
    assert len(grid["depart"]) == 24 and len(grid["tof"]) == 16
    assert np.isfinite(grid["dv"]).sum() > 0
    assert grid["best"] is not None


# --------------------------------------------------------------------------
# Mission lifecycle
# --------------------------------------------------------------------------

@pytest.mark.parametrize("target", TRADE_TARGETS)
def test_full_round_trip_completes_and_returns_home(target):
    """Dispatch, transfer, capture, unload, return and dock."""
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    ok, _ = sim.dispatch(sim.ships[0], target)
    assert ok, f"dispatch to {target} refused"
    run_until_idle(sim)

    assert sim.stats["runs_completed"] == 1, f"{target}: {sim.stats}"
    assert sim.stats["mass_delivered"] == pytest.approx(sim.ships[0].capacity)
    report = sim.fleet_report()[0]
    assert report["at"] == BODIES["colony"].name
    assert report["status"] == Leg.PARKED.value
    assert sim.stats["delta_v_spent"] > 0.0


def test_delta_v_budget_is_conserved():
    """Spent plus remaining must equal the starting budget exactly."""
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    ship = sim.ships[0]
    sim.dispatch(ship, "inner_belt")
    run_until_idle(sim)
    assert sim.stats["delta_v_spent"] + ship.delta_v == pytest.approx(SHIP_START_DELTA_V, rel=1e-9)


def test_outbound_burns_match_the_planned_costs():
    """Departure and arrival-match burns must equal what the plan predicted.

    This is the regression guard for two real bugs: evaluating capture at the
    stepped time instead of the exact arrival instant (which inflated the
    match burn by an order of magnitude), and burning onto a window whose
    departure date had already passed.
    """
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    outbound, return_window = sim.plan_round_trip("colony", "inner_belt")
    assert outbound is not None and return_window is not None
    departure_burn = outbound.dv_depart * AU_PER_YEAR_TO_KM_S * 1000.0
    arrival_burn = outbound.dv_arrive * AU_PER_YEAR_TO_KM_S * 1000.0
    ship = sim.ships[0]
    ok, message = sim.dispatch(ship, "inner_belt")
    assert ok, message
    mission = sim.missions["Kestrel"]
    # Step to just past arrival so only the two outbound burns have happened.
    arrival = mission.departure_time + mission.tof
    sim.step((arrival - sim.time) / SIM_SECONDS_PER_DAY + 0.01)
    assert sim.stats["delta_v_spent"] == pytest.approx(departure_burn + arrival_burn, rel=1e-6)
    assert mission.leg in (Leg.WAITING, Leg.INBOUND)
    # The cargo was handed over at capture.
    assert sim.stats["mass_delivered"] == pytest.approx(ship.capacity)


def test_departure_is_deferred_until_the_window_opens():
    """Burning before the planned departure date would fly the wrong conic."""
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    window = sim.launch_window("colony", "metallic_belt")
    ship = sim.ships[0]
    sim.dispatch(ship, "metallic_belt")
    mission = sim.missions["Kestrel"]
    assert mission.leg is Leg.PENDING
    assert mission.departure_time >= window.departure_time - 1e-9
    # Halfway to the window nothing has burned yet.
    sim.step((window.departure_time - sim.time) / SIM_SECONDS_PER_DAY * 0.5)
    assert mission.leg is Leg.PENDING
    assert ship.delta_v == pytest.approx(SHIP_START_DELTA_V)


def test_dispatch_refuses_over_budget_missions():
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    sim.ships[0].delta_v = 50.0  # essentially dry
    ok, message = sim.dispatch(sim.ships[0], "derelict_zone")
    assert not ok
    assert "m/s" in message
    assert "Kestrel" not in sim.missions


def test_dispatch_refuses_duplicate_and_self_missions():
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    ok, _ = sim.dispatch(sim.ships[0], "inner_belt")
    assert ok
    ok, message = sim.dispatch(sim.ships[0], "inner_belt")
    assert not ok and "already flying" in message

    sim2 = OrbitalSimulation(ship_names=("Kestrel",))
    ok, message = sim2.dispatch(sim2.ships[0], "colony")
    assert not ok


def test_dispatch_refuses_a_mission_the_ship_cannot_return_from():
    """Dispatch prices the whole round trip, not just the outbound leg.

    Letting a ship leave on a one-way budget is what grounded the fleet in
    earlier revisions: it delivered, then sat at the target forever.
    """
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    ship = sim.ships[0]
    outbound, return_window = sim.plan_round_trip("colony", "derelict_zone")
    one_way = outbound.total_delta_v * AU_PER_YEAR_TO_KM_S * 1000.0
    ship.delta_v = one_way + 200.0  # enough to arrive, not to come home
    ok, message = sim.dispatch(ship, "derelict_zone")
    assert not ok
    assert "m/s" in message
    assert "Kestrel" not in sim.missions

    # With the return leg funded as well, the same run is accepted.
    round_trip = one_way + return_window.total_delta_v * AU_PER_YEAR_TO_KM_S * 1000.0
    ship.delta_v = round_trip + 500.0
    ok, message = sim.dispatch(ship, "derelict_zone")
    assert ok, message
    run_until_idle(sim)
    assert sim.stats["runs_completed"] == 1
    assert sim.fleet_report()[0]["at"] == BODIES["colony"].name


def test_ship_that_runs_dry_mid_return_is_left_drifting():
    """If the docking match cannot be paid, the ship does not silently dock."""
    sim = OrbitalSimulation(ship_names=("Kestrel",))
    ship = sim.ships[0]
    ok, _ = sim.dispatch(ship, "inner_belt")
    assert ok
    mission = sim.missions["Kestrel"]

    # Step day by day until the ship has left the target and is inbound, then
    # drain everything except a sliver just before the docking event.
    for _ in range(4000):
        if mission.leg is Leg.INBOUND:
            docking = mission.return_window.dv_arrive * AU_PER_YEAR_TO_KM_S * 1000.0
            ship.delta_v = docking * 0.1
            break
        sim.step(1.0)
    else:
        pytest.fail("ship never reached the inbound leg")

    run_until_idle(sim)
    assert sim.stats["mass_delivered"] > 0.0
    assert any("could not match orbit" in entry.text for entry in sim.log), [e.text for e in sim.log]
    assert ship.name not in sim.missions


def test_two_ships_fly_concurrently_without_interfering():
    sim = OrbitalSimulation(ship_names=("Kestrel", "Petrel"))
    assert sim.dispatch(*[sim.ships[0], "inner_belt"])[0]
    assert sim.dispatch(*[sim.ships[1], "metallic_belt"])[0]
    run_until_idle(sim, dt_days=2.0)
    assert sim.stats["runs_completed"] == 2
    assert sim.stats["mass_delivered"] == pytest.approx(2 * sim.ships[0].capacity)
    assert all(r["at"] == BODIES["colony"].name for r in sim.fleet_report())


def test_ship_report_exposes_hud_fields():
    sim = OrbitalSimulation()
    report = sim.fleet_report()[0]
    for key in ("name", "status", "at", "distance_au", "speed_km_s", "delta_v_left", "cargo", "eta_days"):
        assert key in report, f"HUD field '{key}' missing from ship report"


def test_parked_ship_sits_on_its_body_orbit():
    """Before any burn the freighter must be co-orbiting the colony."""
    sim = OrbitalSimulation()
    report = sim.fleet_report()[0]
    colony_a = BODIES["colony"].elements.a
    assert report["distance_au"] == pytest.approx(colony_a, rel=0.05)
    assert report["speed_km_s"] == pytest.approx(orbital_speed_km_s("colony"), rel=0.05)
