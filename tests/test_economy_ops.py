"""Verification for the colony-operations layer: mining, market, fleet ops.

These modules sit on top of the verified orbital simulation without modifying
it; the tests here pin down the new gameplay rules (depletion curves, market
flooding, hull wear, incidents) and the JSON savegame round trip, while
``tests/test_simulation.py`` continues to guard the astrodynamics core.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import (  # noqa: E402
    MARKET_BASE_PRICES,

    MINING_ORES,
    MINING_VEIN_SIZE_T,
    SHIP_CLASSES,
    SIM_SECONDS_PER_DAY,
)
from src.market import Market  # noqa: E402
from src.mining import (  # noqa: E402
    YieldLedger,
    body_fingerprint,
    mining_hull_factor,
    plan_extraction,
    vein_size,
)
from src.operations import OpsSimulation  # noqa: E402
from src.simulation.bodies import BODIES  # noqa: E402


def run_until_idle(sim: OpsSimulation, dt_days: float = 3.0, max_steps: int = 900) -> None:
    for _ in range(max_steps):
        sim.step(dt_days)
        if not sim.missions:
            return


# --------------------------------------------------------------------------
# Ore fingerprints and depletion
# --------------------------------------------------------------------------

def test_fingerprint_is_deterministic_and_normalised():
    first = body_fingerprint("inner_belt")
    second = body_fingerprint("inner_belt")
    assert first == second
    assert sum(first.values()) == pytest.approx(1.0)
    body_ores = set(BODIES["inner_belt"].resources)
    assert set(first) <= body_ores
    assert set(first) <= set(MINING_ORES)


def test_fingerprints_differ_between_bodies():
    assert body_fingerprint("inner_belt") != body_fingerprint("metallic_belt")
    # The salvage field yields man-made stock, not natural ore.
    assert set(body_fingerprint("derelict_zone")) == {"components", "electronics"}


def test_depletion_reduces_yield_until_the_vein_thins_out():
    ledger = YieldLedger()
    fresh = plan_extraction("metallic_belt", ledger, None, 240.0)
    assert sum(fresh.values()) == pytest.approx(240.0, rel=1e-6)

    # Pull three full vein-sizes of iron out of the field.
    vein = vein_size("metallic_belt", "iron")
    ledger.commit("metallic_belt", {"iron": 3.0 * vein})
    depleted = plan_extraction("metallic_belt", ledger, None, 240.0)
    expected_iron = 240.0 * body_fingerprint("metallic_belt")["iron"] * math.exp(-3.0)
    assert depleted["iron"] == pytest.approx(expected_iron, rel=1e-6)
    assert depleted["iron"] < fresh["iron"]

    # Depletion is per body: a neighbouring field is untouched.
    other = plan_extraction("deep_belt", ledger, None, 240.0)
    assert sum(other.values()) == pytest.approx(240.0, rel=1e-6)


def test_drilling_fills_the_hold_where_scraping_cannot():
    ledger = YieldLedger()
    # A virgin field fills any hold either way: the hold is the hard limit.
    scrape_fresh = plan_extraction("inner_belt", ledger, None, 240.0, mode="scrape")
    drill_fresh = plan_extraction("inner_belt", ledger, None, 240.0, mode="drill")
    assert sum(scrape_fresh.values()) == pytest.approx(240.0)
    assert sum(drill_fresh.values()) == pytest.approx(240.0)

    # Moderately thinned veins (0.4 of a vein size): scraping comes home
    # part-empty while core drilling still fills the hold.
    for ore in ("ice", "iron", "silver"):
        ledger.commit("inner_belt", {ore: 0.4 * vein_size("inner_belt", ore)})
    scrape_thin = plan_extraction("inner_belt", ledger, None, 240.0, mode="scrape")
    drill_thin = plan_extraction("inner_belt", ledger, None, 240.0, mode="drill")
    assert sum(scrape_thin.values()) == pytest.approx(240.0 * math.exp(-0.4), rel=1e-3)
    assert sum(drill_thin.values()) == pytest.approx(240.0)

    # Deep depletion: neither mode fills the hold, but drilling reaches
    # deeper and out-yields scraping.
    for ore in ("ice", "iron", "silver"):
        ledger.commit("inner_belt", {ore: 1.2 * vein_size("inner_belt", ore)})
    scrape_deep = plan_extraction("inner_belt", ledger, None, 240.0, mode="scrape")
    drill_deep = plan_extraction("inner_belt", ledger, None, 240.0, mode="drill")
    assert sum(drill_deep.values()) > sum(scrape_deep.values())
    assert sum(drill_deep.values()) < 240.0


def test_low_hull_mines_less():
    ledger = YieldLedger()
    healthy = plan_extraction("inner_belt", ledger, None, 240.0, hull_pct=100.0)
    worn = plan_extraction("inner_belt", ledger, None, 240.0, hull_pct=20.0)
    assert sum(worn.values()) < sum(healthy.values())
    assert mining_hull_factor(100.0) == 1.0


def test_reservation_stops_two_ships_from_double_booking_a_thin_vein():
    ledger = YieldLedger()
    # Field nearly worked out: only ~50 t of iron equivalent left.
    ledger.commit("inner_belt", {"iron": 2.4 * MINING_VEIN_SIZE_T["iron"]})
    reserved: dict[str, float] = {}
    first = plan_extraction("inner_belt", ledger, reserved, 240.0)
    for ore, t in first.items():
        reserved[ore] = reserved.get(ore, 0.0) + t
    second = plan_extraction("inner_belt", ledger, reserved, 240.0)
    assert sum(second.values()) < sum(first.values())


# --------------------------------------------------------------------------
# Market
# --------------------------------------------------------------------------

def test_market_prices_stay_positive_and_floored():
    market = Market(seed=3)
    for _ in range(2000):
        market.update(1.0)
        market.sell({res: 4000.0 for res in MARKET_BASE_PRICES})
    for res, base in MARKET_BASE_PRICES.items():
        assert market.price(res) >= 0.15 * base - 1e-9


def test_selling_floods_the_price_which_then_recovers():
    market = Market(seed=11)
    for _ in range(120):
        market.update(1.0)
    before = market.price("platinum")
    proceeds, sold = market.sell({"platinum": 600.0})  # 20x absorption
    assert sold["platinum"] == pytest.approx(600.0)
    assert proceeds < 600.0 * before  # flooding degraded the realised price
    after_sale = market.price("platinum")
    assert after_sale < before * 0.35
    for _ in range(240):  # two flood half-lives
        market.update(1.0)
    assert market.price("platinum") > after_sale * 2.0


def test_same_seed_markets_agree_and_json_round_trip_preserves_state():
    a, b = Market(seed=42), Market(seed=42)
    for _ in range(300):
        a.update(2.0)
    restored = Market.from_json(json.loads(json.dumps(a.to_json())))
    for res in MARKET_BASE_PRICES:
        assert restored.price(res) == pytest.approx(a.price(res))
        assert restored.trend(res) == a.trend(res)
    # The restored market keeps producing the same random future as the original.
    for _ in range(50):
        a.update(1.0)
        b.update(1.0)
        restored.update(1.0)
    assert restored.price("iron") == pytest.approx(a.price("iron"))
    assert restored.price("iron") != pytest.approx(b.price("iron"))


def test_quote_is_marginal_but_sell_only_floods_once():
    market = Market(seed=5)
    price = market.price("ice")
    quoted = market.quote("ice", 400.0)
    assert market.flood["ice"] == pytest.approx(0.0)  # a quote commits nothing
    assert quoted <= 400.0 * price
    market.sell({"ice": 400.0})
    assert market.flood["ice"] == pytest.approx(400.0)


# --------------------------------------------------------------------------
# Fleet operations
# --------------------------------------------------------------------------

def test_starting_fleet_matches_the_default_class():
    sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
    spec = SHIP_CLASSES["freighter"]
    for ship in sim.ships:
        assert ship.capacity == spec["capacity"]
        assert ship.delta_v == spec["delta_v"]
        assert sim.hull[ship.name] == 100.0
        assert sim.ship_class[ship.name] == "freighter"


def test_buy_ship_creates_a_distinct_class_and_registry_rejects_unknowns():
    sim = OpsSimulation(ship_names=("Kestrel",))
    ship, message = sim.buy_ship("scout")
    assert ship is not None and ship.capacity == SHIP_CLASSES["scout"]["capacity"]
    assert ship.delta_v == SHIP_CLASSES["scout"]["delta_v"]
    assert sim.ship_class[ship.name] == "scout"
    assert ship.name != "Kestrel"
    again, _ = sim.buy_ship("scout")
    assert again.name != ship.name  # callsigns stay unique
    none, error = sim.buy_ship("battleship")
    assert none is None and "Unknown ship class" in error


def test_dispatch_is_refused_while_the_hull_is_below_critical():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.hull["Kestrel"] = sim.hull_critical_pct - 1.0
    ok, message = sim.dispatch(sim.ships[0], "inner_belt")
    assert not ok and "hull" in message
    assert "Kestrel" not in sim.missions


def test_a_round_trip_wears_the_hull_and_repair_restores_it_for_credits():
    sim = OpsSimulation(ship_names=("Kestrel",))
    ok, _ = sim.dispatch(sim.ships[0], "inner_belt")
    assert ok
    run_until_idle(sim)
    assert sim.hull["Kestrel"] < 100.0

    sim.ships[0].delta_v = 0.0  # parked and drained: refuel and repair
    granted = sim.refuel_docked_fleet(30.0)
    assert granted > 0.0
    hull_before = sim.hull["Kestrel"]
    restored, spent = sim.repair_docked_fleet(10.0, max_credits=1e9)
    assert restored > 0.0
    assert sim.hull["Kestrel"] == pytest.approx(hull_before + restored)
    assert spent == pytest.approx(restored * 12.0, rel=1e-9)
    broke_restored, broke_spent = sim.repair_docked_fleet(10.0, max_credits=0.0)
    assert broke_restored == 0.0 and broke_spent == 0.0


def test_drill_mode_incidents_are_seeded_and_lose_cargo():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.mining_mode = "drill"
    sim.incident_chance_drill = 1.0  # force the incident for the test
    ok, _ = sim.dispatch(sim.ships[0], "inner_belt")
    payload = dict(sim.missions["Kestrel"].cargo)
    assert ok
    run_until_idle(sim)
    assert sim.stats["incidents"] == 1
    assert sim.pending_deliveries[-1].total < sum(payload.values())
    assert sim.hull["Kestrel"] < 90.0  # burns + drilling wear


def test_clean_mode_never_rolls_incidents():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.incident_chance_scrape = 0.0
    ok, _ = sim.dispatch(sim.ships[0], "inner_belt")
    assert ok
    run_until_idle(sim)
    assert sim.stats["incidents"] == 0
    assert sim.stats["ore_mined_t"] == pytest.approx(sim.pending_deliveries[-1].total)


def test_a_stranded_ship_never_depletes_the_vein():
    sim = OpsSimulation(ship_names=("Kestrel",))
    ok, _ = sim.dispatch(sim.ships[0], "metallic_belt")
    assert ok
    assert sim.reserved  # the vein is spoken for while the ship flies
    sim.ships[0].delta_v = 100.0  # not enough for the capture match
    run_until_idle(sim)
    assert sim.ledger.extracted == {}
    assert sim.reserved == {}
    assert sim.pending_deliveries == []


def test_inflight_reservation_shows_up_in_dispatch_planning():
    sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
    ok1, _ = sim.dispatch(sim.ships[0], "inner_belt")
    ok2, _ = sim.dispatch(sim.ships[1], "inner_belt")
    assert ok1 and ok2
    # Both holds were planned against the same veins, so the second run was
    # planned against the field the first ship already booked.
    first = sim.missions["Kestrel"].cargo
    second = sim.missions["Petrel"].cargo
    for ore, tonnes in second.items():
        assert tonnes <= first.get(ore, 0.0) + 1e-6


def test_ship_report_exposes_operations_fields():
    sim = OpsSimulation(ship_names=("Kestrel",))
    report = sim.ship_report(sim.ships[0])
    assert report["class"] == "freighter"
    assert report["hull"] == 100.0
    assert report["capacity"] == SHIP_CLASSES["freighter"]["capacity"]


# --------------------------------------------------------------------------
# Persistence of the operations layer
# --------------------------------------------------------------------------

def test_ops_json_round_trip_and_continued_determinism():
    sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
    sim.dispatch(sim.ships[0], "inner_belt")
    for _ in range(60):
        sim.step(2.0)
    data = json.loads(json.dumps(sim.to_json()))
    restored = OpsSimulation.from_json(data)

    assert restored.time == pytest.approx(sim.time)
    assert {n: m.leg for n, m in restored.missions.items()} == {n: m.leg for n, m in sim.missions.items()}
    assert restored.ledger.extracted == sim.ledger.extracted
    assert restored.reserved == sim.reserved

    for _ in range(40):
        sim.step(2.0)
        restored.step(2.0)
    for live, loaded in zip(sim.ships, restored.ships):
        assert live.r == pytest.approx(loaded.r, abs=1e-12)
        assert live.v == pytest.approx(loaded.v, abs=1e-12)
