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
    LIFE_START_FOOD,
    LIFE_START_OXYGEN,
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
from src.simulation.orbital_sim import Leg  # noqa: E402
from src.simulation.bodies import BODIES, TRADE_TARGETS  # noqa: E402


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


# --------------------------------------------------------------------------
# Crew: rosters, morale, fatigue
# --------------------------------------------------------------------------

def test_every_ship_has_a_named_roster_with_roles():
    sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
    for ship in sim.ships:
        roster = sim.crew[ship.name]
        assert len(roster) == 4
        roles = sorted(member.role for member in roster)
        assert roles == ["engineer", "miner", "miner", "pilot"]
        assert all(member.name and " " in member.name for member in roster)
    assert sim.crew["Kestrel"] is not sim.crew["Petrel"]


def test_fatigue_accumulates_away_and_recovers_at_the_colony():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.dispatch(sim.ships[0], "inner_belt")
    for _ in range(40):
        sim.step(3.0)
        if sim.missions and sim.missions["Kestrel"].leg is not Leg.PENDING:
            break
    _, fatigue = sim.crew_stats("Kestrel")
    assert fatigue > 5.0  # flying accrues fatigue

    while sim.missions:
        sim.step(3.0)
    for _ in range(60):
        sim.step(3.0)
    _, fatigue = sim.crew_stats("Kestrel")
    assert fatigue == pytest.approx(0.0, abs=5.0)


def test_a_long_run_leaves_the_crew_tired_but_recoverable():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.dispatch(sim.ships[0], "inner_belt")
    while sim.missions:
        sim.step(3.0)
    morale, fatigue = sim.crew_stats("Kestrel")
    assert 20.0 < morale < 75.0      # drained, not destroyed
    assert fatigue > 60.0            # genuinely tired
    for _ in range(50):              # a season docked
        sim.step(3.0)
    morale, fatigue = sim.crew_stats("Kestrel")
    assert morale > 45.0 and fatigue < 10.0


def test_exhausted_crew_refuses_dispatch_until_rest():
    sim = OpsSimulation(ship_names=("Kestrel",))
    for member in sim.crew["Kestrel"]:
        member.fatigue = 95.0
    ok, message = sim.dispatch(sim.ships[0], "inner_belt")
    assert not ok and "exhausted" in message
    for _ in range(40):  # ~120 dock days
        sim.step(3.0)
    _, fatigue = sim.crew_stats("Kestrel")
    assert fatigue < 90.0
    ok, _ = sim.dispatch(sim.ships[0], "inner_belt")
    assert ok


def test_unhappy_crew_mines_less_and_crashes_more():
    sim_low = OpsSimulation(ship_names=("Kestrel",))
    for member in sim_low.crew["Kestrel"]:
        member.morale = 0.0
        member.fatigue = 100.0
    sim_high = OpsSimulation(ship_names=("Kestrel",))
    for member in sim_high.crew["Kestrel"]:
        member.morale = 100.0
        member.fatigue = 0.0
    assert sim_low.crew_yield_factor("Kestrel") < sim_high.crew_yield_factor("Kestrel")
    assert sim_low.crew_incident_factor("Kestrel") > sim_high.crew_incident_factor("Kestrel")
    assert sim_high.crew_yield_factor("Kestrel") <= 1.0

    ledger_low = YieldLedger()
    ledger_high = YieldLedger()
    payload_low = plan_extraction("inner_belt", ledger_low, None, 240.0,
                                  mine_bonus=sim_low.crew_yield_factor("Kestrel"))
    payload_high = plan_extraction("inner_belt", ledger_high, None, 240.0,
                                   mine_bonus=sim_high.crew_yield_factor("Kestrel"))
    assert sum(payload_low.values()) < sum(payload_high.values())


def test_capture_pays_morale_and_payday_pays_the_fleet():
    sim = OpsSimulation(ship_names=("Kestrel",))
    for member in sim.crew["Kestrel"]:
        member.morale = 40.0
    sim.dispatch(sim.ships[0], "inner_belt")
    while sim.missions:
        sim.step(3.0)
    morale_after_run = sim.crew_stats("Kestrel")[0]
    assert morale_after_run > 41.0  # the capture bonus is in there
    sim.crew_payday(2.0)
    assert sim.fleet_morale() > morale_after_run


def test_hardship_applies_and_boredom_has_a_floor():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.apply_hardship(30.0)
    assert sim.crew_stats("Kestrel")[0] == pytest.approx(50.0)
    for _ in range(800):  # over two years parked
        sim.step(3.0)
    assert sim.crew_stats("Kestrel")[0] >= 25.0 - 1e-6


# --------------------------------------------------------------------------
# Space weather: flares and debris seasons
# --------------------------------------------------------------------------

def test_flare_lifecycle_progresses_and_returns_to_quiet():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim._flare_timer = 1e-6  # imminent (timers are in sim-seconds: 1 s ~ 58 days)
    seen = set()
    for _ in range(200):
        sim.step(0.5)
        seen.add(sim.flare_state)
        if sim.flare_state == "quiet" and sim.time > 20.0 * SIM_SECONDS_PER_DAY:
            break
    assert {"warning", "flare"} <= seen
    assert sim.flare_state == "quiet"


def test_flare_and_debris_only_wear_ships_in_flight():
    sim = OpsSimulation(ship_names=("Kestrel", "Petrel"))
    sim.dispatch(sim.ships[0], "inner_belt")
    while sim.missions["Kestrel"].leg is Leg.PENDING:  # wait for the burn
        sim.step(1.0)
    sim.flare_state = "flare"
    sim._flare_duration = 1e9  # hold the flare open for the test
    sim.debris_active = True
    sim._debris_timer = 1e9
    hull_parked = sim.hull["Petrel"]
    for _ in range(20):
        sim.step(1.0)
    assert sim.hull["Kestrel"] < 100.0 - 20.0  # flying: ~1.55%/day for 20 days
    assert sim.hull["Petrel"] == pytest.approx(hull_parked)  # docked: shielded
    assert sim.weather_alert()


def test_weather_state_survives_a_json_round_trip():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.flare_state = "warning"
    sim._flare_timer = 42.0
    sim.debris_active = True
    sim._debris_timer = 77.0
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert restored.flare_state == "warning"
    assert restored._flare_timer == pytest.approx(42.0)
    assert restored.debris_active is True
    assert restored._debris_timer == pytest.approx(77.0)
    assert [m.to_json() for m in restored.crew["Kestrel"]] == [m.to_json() for m in sim.crew["Kestrel"]]


# --------------------------------------------------------------------------
# Earth faction contracts and reputation
# --------------------------------------------------------------------------

def test_contract_lifecycle_through_the_game():
    from src.main import Game

    game = Game(headless=True)
    game.market.day = 100.0  # force the offer window open
    game.contracts._next_offer_day = 50.0
    offer = game.contracts.maybe_offer()
    assert offer is not None
    assert offer.resource in MARKET_BASE_PRICES
    assert offer.reward_credits > 0.0
    # Offers wait for the director: pending, not active.
    assert game.contracts.active == []
    assert game.contracts.accept(offer.id) is offer
    assert [c.id for c in game.contracts.active] == [offer.id]

    credits_before = game.credits
    # Half the order is not enough to complete it.
    partial = game.contracts.register_delivery({offer.resource: offer.tonnes / 2.0})
    assert partial == []
    assert game.contracts.active[0].progress == pytest.approx(offer.tonnes / 2.0)
    assert game.credits == credits_before

    for completed in game.contracts.register_delivery({offer.resource: offer.tonnes}):
        game.credits += game.contracts.complete(completed)
    assert game.credits > credits_before
    assert game.contracts.reputation[offer.faction] == pytest.approx(12.0)
    assert not game.contracts.active


def test_overdue_orders_cost_reputation():
    from src.main import Game

    game = Game(headless=True)
    game.market.day = 100.0
    game.contracts._next_offer_day = 50.0
    offer = game.contracts.maybe_offer()
    assert offer is not None
    assert game.contracts.accept(offer.id) is offer
    game.market.day = offer.deadline_day + 1.0
    overdue = game.contracts.expire_overdue()
    assert [c.id for c in overdue] == [offer.id]
    assert game.contracts.reputation[offer.faction] == pytest.approx(-18.0)
    assert game.contracts.price_multiplier() < 1.0


def test_reputation_moves_sale_proceeds():
    from src.main import Game

    low, high = Game(headless=True), Game(headless=True)
    for faction in low.contracts.reputation:
        low.contracts.reputation[faction] = -100.0
        high.contracts.reputation[faction] = 100.0
    assert high.contracts.price_multiplier() > low.contracts.price_multiplier()
    lots = {"iron": 100.0}
    proceeds_low, _ = low.market.sell(dict(lots))
    proceeds_high, _ = high.market.sell(dict(lots))
    assert proceeds_high * high.contracts.price_multiplier() > proceeds_low * low.contracts.price_multiplier()


def test_sell_all_holds_back_the_life_support_ice_reserve():
    from src.config import LIFE_ICE_RESERVE_T
    from src.main import Game

    game = Game(headless=True)
    game.colony.state["resources"]["ice"] = LIFE_ICE_RESERVE_T + 50.0
    game.sell_all()
    assert game.colony.state["resources"]["ice"] == pytest.approx(LIFE_ICE_RESERVE_T)


# --------------------------------------------------------------------------
# Colony life support
# --------------------------------------------------------------------------

def test_life_support_keeps_oxygen_and_food_up_while_ice_remains():
    from src.main import Game

    game = Game(headless=True)
    oxygen, food = [], []
    for _ in range(120):
        game.update(2.0)
        oxygen.append(game.colony.state["resources"]["oxygen"])
        food.append(game.colony.state["resources"]["food"])
    # Production covers the crew while the ice refinery feeds water in.
    assert min(oxygen) > 0.5 * LIFE_START_OXYGEN
    assert min(food) > 0.5 * LIFE_START_FOOD
    # With recycling the melt is small, but the refinery must be running.
    assert game.colony.state["resources"]["ice"] < 199.0
    assert not getattr(game, "_life_shortage_flag", False)


def test_life_support_shortage_grinds_morale():
    from src.main import Game

    game = Game(headless=True)
    resources = game.colony.state["resources"]
    resources.update({"oxygen": 0.0, "food": 0.0, "water": 0.0, "ice": 0.0, "energy": 0.0})
    morale_before = game.sim.fleet_morale()
    for _ in range(30):
        game.update(1.0)
    assert game._life_shortage_flag
    assert game.sim.fleet_morale() < morale_before - 10.0


# --------------------------------------------------------------------------
# Value-aware auto-dispatch and the orientation checklist
# --------------------------------------------------------------------------

def test_auto_dispatch_chooses_a_target_and_skips_worked_out_veins():
    from src.main import Game
    from src.mining import body_fingerprint, vein_size

    game = Game(headless=True)
    ship = game.sim.ships[0]
    assert game._choose_auto_target(ship) in TRADE_TARGETS

    # Work every field to nothing: with no vein left the planned hold is
    # empty, so the dispatcher has nothing worth flying.
    for key in TRADE_TARGETS:
        game.sim.ledger.extracted[key] = {
            ore: 40.0 * vein_size(key, ore) for ore in body_fingerprint(key)
        }
    assert game._estimate_run_value(TRADE_TARGETS[0], ship) == pytest.approx(0.0)
    assert game._choose_auto_target(ship) is None


def test_tutorial_walks_the_whole_checklist(monkeypatch, tmp_path):
    from src.game import savegame as colony_savegame
    from src.main import Game

    monkeypatch.setattr(colony_savegame, "SAVE_DIR", str(tmp_path))
    game = Game(headless=True)
    game.update(1.0)
    # The auto-dispatcher launches a fuelled ship on its own, so the first
    # checklist step completes without the player pressing ENTER.
    assert game._tut["dispatched"]
    assert "S" in game.tutorial_text
    game.sell_all()
    game.update(1.0)
    assert "X" in game.tutorial_text
    game.toggle_drill()
    game.update(1.0)
    assert "1-4" in game.tutorial_text
    game.credits = 99999.0
    game.buy_ship_class("scout")
    game.update(1.0)
    assert "F5" in game.tutorial_text
    game.save_game("tutorial")
    game.update(1.0)
    assert game._tut["done"] and game.tutorial_text == ""


# --------------------------------------------------------------------------
# Procedural audio synthesis
# --------------------------------------------------------------------------

def test_procedural_alerts_and_hum_are_valid_wav_files(tmp_path):
    import wave

    from src.utils.procedural import make_alert_wav, make_hum_wav

    for kind in ("flare", "hull", "shortage", "contract"):
        path = make_alert_wav(kind, str(tmp_path / f"{kind}.wav"))
        with wave.open(path) as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == 22050
            assert handle.getnframes() > 1000

    with pytest.raises(ValueError):
        make_alert_wav("kaiju", str(tmp_path / "bad.wav"))

    hum_path = make_hum_wav(str(tmp_path / "hum.wav"))
    with wave.open(hum_path) as handle:
        seconds = handle.getnframes() / handle.getframerate()
        assert 2.0 < seconds < 6.0  # a short seamless loop


def test_audio_tick_is_a_noop_without_audio_objects():
    from src.main import Game

    game = Game(headless=True)
    game.audio = None
    game.update(1.0)  # must not raise
    assert game.power_load >= 0.05


# --------------------------------------------------------------------------
# Crew specialisations
# --------------------------------------------------------------------------

def test_hire_fire_and_role_effects():
    sim = OpsSimulation(ship_names=("Kestrel",))
    # The template roster already flies with one pilot: 3% discount.
    assert sim.pilots_discount("Kestrel") > 0.0
    ok, _ = sim.hire("pilot", "Kestrel")
    assert ok and sim.pilots_discount("Kestrel") > 0.03
    # Botanists work the colony, not a ship.
    base = sim.botanist_water_factor()
    sim.hire("botanist")
    sim.hire("botanist")
    assert sim.botanist_water_factor() < base
    # Firing hurts the survivors; the last seat is protected.
    eng = next(m for m in sim.crew["Kestrel"] if m.role == "engineer")
    before = sim.crew_stats("Kestrel")[0]
    ok, _ = sim.fire("Kestrel", eng)
    assert ok and not sim.has_engineer("Kestrel")
    assert sim.crew_stats("Kestrel")[0] < before
    last = sim.crew["Kestrel"][0]
    sim.crew["Kestrel"] = [last]
    ok, _ = sim.fire("Kestrel", last)
    assert not ok and last in sim.crew["Kestrel"]


def test_pilots_refund_propellant_the_core_billed():
    plain, staffed = OpsSimulation(ship_names=("Kestrel",)), OpsSimulation(ship_names=("Kestrel",))
    plain.dispatch(plain.ships[0], "inner_belt")
    staffed.dispatch(staffed.ships[0], "inner_belt")
    staffed.hire("pilot", "Kestrel")
    staffed.hire("pilot", "Kestrel")
    # Fly both to the departure burn and compare the billed propellant.
    for _ in range(80):
        plain.step(3.0)
        staffed.step(3.0)
    assert plain.ships[0].delta_v < staffed.ships[0].delta_v  # pilots saved fuel


def test_engineers_speed_repairs():
    fast, slow = OpsSimulation(ship_names=("Kestrel",)), OpsSimulation(ship_names=("Kestrel",))
    # The template carries an engineer; strip the slow ship's so the compare
    # is engineer vs no engineer.
    slow.crew["Kestrel"] = [m for m in slow.crew["Kestrel"] if m.role != "engineer"]
    for sim in (fast, slow):
        sim.hull["Kestrel"] = 50.0
    fast.repair_docked_fleet(5.0, max_credits=1e9)
    slow.repair_docked_fleet(5.0, max_credits=1e9)
    assert fast.hull["Kestrel"] > slow.hull["Kestrel"]


# --------------------------------------------------------------------------
# Gravitational perturbations
# --------------------------------------------------------------------------

def test_perturbation_shifts_only_this_sims_bodies_and_drops_caches():
    from src.simulation.bodies import BODIES as MODULE_BODIES

    sim = OpsSimulation(ship_names=("Kestrel",))
    sim._perturb_timer = 1e-6
    sim.step(0.5)
    changed = [key for key in TRADE_TARGETS
               if sim.bodies[key].elements.a != MODULE_BODIES[key].elements.a]
    assert changed, "the perturbation should have moved one body"
    assert not sim._window_cache and not sim._round_trip_cache
    assert any("perturbation" in entry.text for entry in sim.log)
    # The module-level table the verified tests read is untouched.
    for key in TRADE_TARGETS:
        assert MODULE_BODIES[key].elements.a == BODIES[key].elements.a


def test_perturbed_elements_survive_a_save():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim._perturb_timer = 1e-6
    sim.step(0.5)
    moved = next(key for key in TRADE_TARGETS
                 if sim.bodies[key].elements.a != BODIES[key].elements.a)
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert restored.bodies[moved].elements.a == pytest.approx(sim.bodies[moved].elements.a)
    assert restored.bodies[moved].elements.a != pytest.approx(BODIES[moved].elements.a)


# --------------------------------------------------------------------------
# Contract negotiation
# --------------------------------------------------------------------------

def test_offers_wait_for_accept_decline_and_expiry():
    from src.main import Game

    game = Game(headless=True)
    game.market.day = 100.0
    game.contracts._next_offer_day = 50.0
    offer = game.contracts.maybe_offer()
    assert offer is not None and game.contracts.active == []
    # Declining clears the desk with no reputation change.
    assert game.contracts.decline(offer.id) is offer
    assert game.contracts.pending == [] and sum(game.contracts.reputation.values()) == 0.0

    # A second offer can be accepted, and stale ones are withdrawn.
    game.contracts._next_offer_day = 50.0  # reopen the offer window for the test
    offer2 = game.contracts.maybe_offer()
    assert offer2 is not None
    game.market.day = offer2.deadline_day - 29.0
    stale = game.contracts.expire_pending()
    assert [c.id for c in stale] == [offer2.id]


def test_headless_autopilot_accepts_fillable_offers():
    from src.main import Game

    game = Game(headless=True)
    game.market.day = 100.0
    game.contracts._next_offer_day = 50.0
    # Earth offers only what the fleet trades; seed a recent iron delivery.
    # The autopilot drains pending offers in the same tick, so watch the
    # active book.
    game._recent_deliveries["iron"] = 90.0
    accepted_iron = False
    while game.market.day < 400.0:
        game.market.update(1.0)
        game._tick_contracts()
        if any(c.resource == "iron" for c in game.contracts.active):
            accepted_iron = True
            break
    assert accepted_iron, "the autopilot should accept an order it can fill"
    assert not any(c.resource == "iron" for c in game.contracts.pending)


# --------------------------------------------------------------------------
# Jump-to-event and audio polish
# --------------------------------------------------------------------------

def test_jump_to_event_races_warp_and_restores_it():
    from src.config import TIME_WARP_STEPS
    from src.main import Game

    game = Game(headless=True)
    game.sim.dispatch(game.sim.ships[0], "inner_belt")
    game.update(1.0)
    assert game.upcoming_events()
    slow_warp = game.sim.warp_days_per_second
    game.cycle_jump()
    assert game._jump_target is not None
    assert game.sim.warp_days_per_second == max(TIME_WARP_STEPS)
    # Race ahead: warp restores once the moment passes.
    for _ in range(4000):
        game.update(3.0)
        if game._jump_target is None:
            break
    assert game._jump_target is None
    assert game.sim.warp_days_per_second == slow_warp


def test_audio_mute_and_ducking_with_a_stub_mixer():
    from src.main import Game

    class StubSound:
        def __init__(self):
            self.volume, self.pitch, self.played = 0.0, 1.0, 0

        def play(self):
            self.played += 1

    game = Game(headless=True)
    game.audio = {"hum": StubSound(), "flare": StubSound(), "hull": StubSound(),
                  "shortage": StubSound(), "contract": StubSound()}
    game.power_load = 0.8
    game.toggle_mute()
    game._tick_audio()
    assert game.audio["hum"].volume == 0.0          # muted hum is silent
    game.toggle_mute()
    game.sim.flare_state = "warning"                 # rising edge plays once
    game._tick_audio()
    assert game.audio["flare"].played == 1
    # The next tick ducks the hum under the alert that just fired; the alert
    # re-fires because the edge flag was cleared externally.
    game._alert_edges["flare"] = False
    game._tick_audio()
    assert game.audio["flare"].played == 2
    assert game.audio["hum"].volume < 0.15 + 0.55 * 0.8  # ducked


# --------------------------------------------------------------------------
# Multi-revolution planning in the campaign layer
# --------------------------------------------------------------------------

def test_forced_multi_rev_mission_flies_and_delivers():
    """With the saving gate forced open the plan adopts slow 1-revolution
    routes. They cost 2-4x a single-rev round trip (Hohmann-class windows
    dominate this near-coplanar network), so a deep-budget ship flies it:
    the point is proving the event system, burn billing and capture handle
    multi-rev arcs end to end."""
    from src.config import SIM_SECONDS_PER_DAY

    sim = OpsSimulation(ship_names=("Kestrel",))
    sim._multi_rev_min_saving = -100.0  # force adoption when a branch exists
    sim.ships[0].delta_v = 500_000.0    # a deep propellant budget for the slow route
    ok, _ = sim.dispatch(sim.ships[0], "derelict_zone")
    assert ok
    mission = sim.missions["Kestrel"]
    assert mission.return_window.revs == 1
    window_days = mission.tof / SIM_SECONDS_PER_DAY
    assert window_days > 200.0  # well beyond the single-rev ~144 d arc

    deliveries = 0
    for _ in range(900):
        sim.step(3.0)
        if sim.pending_deliveries:
            deliveries += 1
            sim.pending_deliveries.clear()
        if not sim.missions:
            break
    assert deliveries >= 1
    report = sim.ship_report(sim.ships[0])
    assert report["status"] in ("parked", "waiting")


def test_planning_knobs_survive_a_json_round_trip():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.dispatch(sim.ships[0], "inner_belt")
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert restored._max_revs == sim._max_revs
    assert restored._multi_rev_min_saving == sim._multi_rev_min_saving
    assert restored.missions["Kestrel"].return_window.revs == \
        sim.missions["Kestrel"].return_window.revs


# --------------------------------------------------------------------------
# Refuel depots
# --------------------------------------------------------------------------

def test_depot_enables_a_run_the_ship_cannot_afford_alone():
    from src.config import SIM_SECONDS_PER_DAY

    sim = OpsSimulation(ship_names=("Hauler",), ship_classes={"Hauler": "hauler"})
    rt_cost = sim.round_trip_cost_ms("colony", "deep_belt")
    assert rt_cost is not None and rt_cost > sim.ships[0].delta_v  # beyond the tank
    ok, _ = sim.dispatch(sim.ships[0], "deep_belt")
    assert not ok
    sim.build_depot("deep_belt")
    ok, _ = sim.dispatch(sim.ships[0], "deep_belt")
    assert ok
    # The bond is a loan: the visible tank must show the real propellant.
    assert sim.ships[0].delta_v == SHIP_CLASSES["hauler"]["delta_v"]
    for _ in range(6000):
        sim.step(3.0)
        if not sim.missions:
            break
    report = sim.ship_report(sim.ships[0])
    assert report["at_key"] == "colony"  # made it home on the depot top-up


def test_depot_refuses_to_back_a_run_when_the_tank_is_short():
    sim = OpsSimulation(ship_names=("Hauler",), ship_classes={"Hauler": "hauler"})
    sim.build_depot("deep_belt")
    sim.depots["deep_belt"].fuel_ms = 100.0  # not enough for the ride home
    ok, _ = sim.dispatch(sim.ships[0], "deep_belt")
    assert not ok


def test_depot_generation_refills_and_clips_at_capacity():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.build_depot("metallic_belt")
    depot = sim.depots["metallic_belt"]
    depot.fuel_ms = 0.0
    for _ in range(100):
        sim.tick_depots(1.0)
    assert 0.0 < depot.fuel_ms <= depot.capacity
    depot.fuel_ms = depot.capacity
    for _ in range(50):
        sim.tick_depots(1.0)
    assert depot.fuel_ms == depot.capacity


def test_depot_upgrade_scales_level_and_cost():
    sim = OpsSimulation(ship_names=("Kestrel",))
    assert sim.depot_upgrade_cost("inner_belt") == 3500.0
    sim.build_depot("inner_belt")
    assert sim.depots["inner_belt"].level == 1
    first_upgrade = sim.depot_upgrade_cost("inner_belt")
    sim.build_depot("inner_belt")
    assert sim.depots["inner_belt"].level == 2
    assert sim.depot_upgrade_cost("inner_belt") > first_upgrade
    ok, _ = sim.build_depot("colony")
    assert not ok  # the colony is not a trade target


def test_depots_survive_a_json_round_trip():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.build_depot("deep_belt")
    sim.depots["deep_belt"].fuel_ms = 12345.0
    sim.depots["deep_belt"].level = 2
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert restored.depots["deep_belt"].fuel_ms == pytest.approx(12345.0)
    assert restored.depots["deep_belt"].level == 2


def test_game_build_depot_pays_and_reports():
    from src.main import Game

    game = Game(headless=True)
    game.update(1.0)  # ensures the HUD target feed exists
    game.credits = 4000.0
    game.build_depot_selected()
    assert game.credits == pytest.approx(4000.0 - 3500.0)
    assert len(game.sim.depots) == 1
    broke = Game(headless=True)
    broke.credits = 10.0
    broke.update(1.0)
    broke.build_depot_selected()
    assert not broke.sim.depots


# --------------------------------------------------------------------------
# The comet
# --------------------------------------------------------------------------

def test_comet_lives_in_the_campaign_not_the_module_table():
    from src.simulation.bodies import BODIES as MODULE_BODIES

    sim = OpsSimulation(ship_names=("Kestrel",))
    assert "comet_vigil" in sim.bodies and "comet_vigil" in sim.trade_targets
    assert "comet_vigil" not in MODULE_BODIES  # the verified table is pristine
    assert sim.bodies["comet_vigil"].elements.e > 0.7  # genuinely eccentric


def test_comet_windows_are_rare_and_expensive_but_real():
    from src.config import SIM_SECONDS_PER_DAY

    sim = OpsSimulation(ship_names=("Scout",), ship_classes={"Scout": "scout"})
    window = sim.launch_window("colony", "comet_vigil")
    assert window is not None
    assert window.tof / SIM_SECONDS_PER_DAY > 120.0  # a long arc
    rt = sim.round_trip_cost_ms("colony", "comet_vigil")
    assert rt is not None and rt > SHIP_CLASSES["freighter"]["delta_v"]
    assert rt < SHIP_CLASSES["scout"]["delta_v"] * 1.15  # a scout can do it


def test_comet_ore_is_primordial_ice_and_platinum():
    from src.mining import body_fingerprint, plan_extraction, vein_size

    fingerprint = body_fingerprint("comet_vigil")
    assert set(fingerprint) == {"ice", "platinum"}
    assert vein_size("comet_vigil", "platinum") > 0
    ledger = YieldLedger()
    payload = plan_extraction("comet_vigil", ledger, None, 240.0)
    assert sum(payload.values()) == pytest.approx(240.0)


def test_comet_survives_a_json_round_trip():
    sim = OpsSimulation(ship_names=("Kestrel",))
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert "comet_vigil" in restored.bodies
    assert restored.bodies["comet_vigil"].elements.a == pytest.approx(
        sim.bodies["comet_vigil"].elements.a)


def test_windows_board_lists_every_campaign_target():
    from src.main import Game

    game = Game(headless=True)
    game.update(1.0)
    game._update_windows_board()
    names = {name for name, _, _ in game._windows_board}
    for key in game.sim.trade_targets:
        assert game.sim.bodies[key].name in names
    days = [days for _, days, _ in game._windows_board]
    assert days == sorted(days)  # soonest first


# --------------------------------------------------------------------------
# Parts market, ship upgrades and depot drone bays
# --------------------------------------------------------------------------

def test_part_prices_scale_with_season_and_count():
    early, late = Market(seed=3), Market(seed=3)
    p0 = early.part_price("tank")
    for _ in range(150):
        late.update(1.0)
    p1 = late.part_price("tank")
    assert p0 > 0.0 and p1 > 0.0
    assert late.part_price("tank", already_owned=1) > late.part_price("tank", already_owned=0)


def test_ship_upgrades_change_the_numbers_they_claim_to():
    sim = OpsSimulation(ship_names=("Kestrel",))
    base_dv = sim.effective_delta_v("Kestrel")
    sim.install_part("Kestrel", "tank")
    assert sim.effective_delta_v("Kestrel") == base_dv + 3500.0
    sim.install_part("Kestrel", "drill")
    assert sim.ship_mine_bonus("Kestrel") > 1.0
    sim.install_part("Kestrel", "quarters")
    assert sim.crew_rest_factor("Kestrel") > 1.0
    # Caps: two tanks, two drills, one quarters.
    sim.install_part("Kestrel", "tank")
    assert sim.effective_delta_v("Kestrel") == base_dv + 7000.0
    ok, _ = sim.install_part("Kestrel", "tank")
    assert not ok
    ok, _ = sim.install_part("Kestrel", "quarters")
    assert not ok


def test_refuel_fills_drop_tanks_too():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.install_part("Kestrel", "tank")
    sim.ships[0].delta_v = 0.0
    sim.refuel_docked_fleet(400.0)
    assert sim.ships[0].delta_v == pytest.approx(sim.effective_delta_v("Kestrel"), abs=1.0)


def test_game_buy_part_bills_and_installs():
    from src.main import Game

    game = Game(headless=True)
    game.credits = 20000.0
    game.buy_part("tank")  # buy while the fleet is still docked
    assert sum(game.sim.upgrades.get("Kestrel", {}).values()) == 1
    assert game.credits < 20000.0
    game.update(1.0)  # the dispatcher may now fly a bigger tank outward


def test_depot_drones_fill_a_waiting_ship():
    from src.config import SIM_SECONDS_PER_DAY

    sim = OpsSimulation(ship_names=("Hauler",), ship_classes={"Hauler": "hauler"})
    ship = sim.ships[0]
    sim.build_depot("inner_belt")
    sim.install_depot_part("inner_belt", "drones")
    assert sim.depots["inner_belt"].upgrades.get("drones") == 1
    ok, _ = sim.dispatch(ship, "inner_belt")
    assert ok
    peak = 0.0
    for _ in range(4000):
        sim.step(3.0)
        peak = max(peak, ship.cargo_load)
        if not sim.missions:
            break
    # The ship held at the depot long enough for the drones to work it full.
    assert peak > ship.capacity * 0.5
    assert sim.ledger.extracted.get("inner_belt")  # veins drawn honestly
    report = sim.ship_report(ship)
    assert report["at_key"] == "colony"  # and it made it home


def test_drone_bay_requires_a_depot_and_respects_its_cap():
    sim = OpsSimulation(ship_names=("Kestrel",))
    ok, _ = sim.install_depot_part("inner_belt", "drones")
    assert not ok
    sim.build_depot("inner_belt")
    sim.install_depot_part("inner_belt", "drones")
    sim.install_depot_part("inner_belt", "drones")
    ok, _ = sim.install_depot_part("inner_belt", "drones")
    assert not ok  # max_per_depot = 2


def test_upgrades_survive_a_json_round_trip():
    sim = OpsSimulation(ship_names=("Kestrel",))
    sim.install_part("Kestrel", "tank")
    sim.install_part("Kestrel", "drill")
    sim.build_depot("deep_belt")
    sim.install_depot_part("deep_belt", "drones")
    restored = OpsSimulation.from_json(json.loads(json.dumps(sim.to_json())))
    assert restored.upgrades["Kestrel"] == {"tank": 1, "drill": 1}
    assert restored.depots["deep_belt"].upgrades == {"drones": 1}
    assert restored.effective_delta_v("Kestrel") == sim.effective_delta_v("Kestrel")


# --------------------------------------------------------------------------
# The whole vertical slice through the real Game loop
# --------------------------------------------------------------------------

def test_vertical_slice_mine_deliver_sell_buy():
    from src.config import START_CREDITS
    from src.main import Game

    game = Game(headless=True)
    assert game.credits == START_CREDITS
    game.sim.dispatch(game.sim.ships[0], "inner_belt")
    game.sim.dispatch(game.sim.ships[1], "metallic_belt")
    for _ in range(700):
        game.update(3.0)

    assert game.deliveries_booked >= 2
    assert game.colony.summary()["used"] > 100.0
    assert game.sim.stats["ore_mined_t"] > 0.0

    # Sell the holds: the treasury must respond.
    treasury_before = game.credits
    game.sell_all()
    assert game.credits > treasury_before + 1000.0
    # Selling drained the marketable stock.
    resources = game.colony.state["resources"]
    assert resources["iron"] < 1.0 and resources["silver"] < 1.0

    # Reinvest: a purchased scout joins the fleet and pays the bill.
    fleet_before = len(game.sim.ships)
    game.credits = 10_000.0
    game.buy_ship_class("scout")
    assert len(game.sim.ships) == fleet_before + 1
    assert game.credits == pytest.approx(10_000.0 - SHIP_CLASSES["scout"]["price"])


def test_game_save_and_load_round_trip(monkeypatch, tmp_path):
    from src.game import savegame as colony_savegame
    from src.main import Game

    monkeypatch.setattr(colony_savegame, "SAVE_DIR", str(tmp_path))
    game = Game(headless=True)
    game.sim.dispatch(game.sim.ships[0], "inner_belt")
    for _ in range(80):
        game.update(3.0)

    saved_credits = game.credits
    saved_time = game.sim.time
    saved_price = game.market.price("iron")
    saved_ledger = json.loads(json.dumps(game.sim.ledger.to_json()))
    game.save_game("test")

    # Diverge hard after the save.
    game.credits = 1.0
    game.sell_all()
    game.sim.hull["Kestrel"] = 7.0
    for _ in range(30):
        game.update(3.0)
    assert game.sim.time > saved_time + 30.0 * SIM_SECONDS_PER_DAY

    game.load_game("test")
    assert game.credits == pytest.approx(saved_credits)
    assert game.sim.time == pytest.approx(saved_time)
    assert game.market.price("iron") == pytest.approx(saved_price)
    assert game.sim.ledger.to_json() == saved_ledger

    # The loaded game keeps flying the mission it was saved in the middle of.
    deliveries_before = game.deliveries_booked
    for _ in range(700):
        game.update(3.0)
    assert game.deliveries_booked > deliveries_before
