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

The base class remains directly constructible and behaves exactly as before;
every extension here is additive.
"""

from __future__ import annotations

import random


import numpy as np

from .config import (
    DEFAULT_SHIP_CLASS,
    FLEET_NAME_POOL,
    HULL_CRITICAL_PCT,
    HULL_MAX_PCT,
    HULL_MIN_PCT,
    HULL_REPAIR_COST_PER_PCT,
    HULL_REPAIR_RATE_PCT_PER_DAY,
    HULL_WEAR_PCT_PER_MS,
    INCIDENT_CHANCE_DRILL,
    INCIDENT_CHANCE_SCRAPE,
    INCIDENT_CARGO_LOSS,
    INCIDENT_LOW_HULL_FACTOR,
    MINING_DRILL_WEAR_PCT,
    MINING_LOW_HULL_YIELD_PCT,
    MINING_RECOVERY_TAU_DAYS,
    SHIP_CLASSES,
)
from .market import rng_from_json, rng_to_json
from .maths import windows as window_solver
from .mining import YieldLedger, plan_extraction
from .simulation.bodies import BODIES
from .simulation.orbital_sim import Delivery, Leg, LogEntry, Mission, OrbitalSimulation, Ship


class OpsSimulation(OrbitalSimulation):
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
        # Per-instance knobs so tests can tighten probabilities without
        # touching global config.
        self.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        self.incident_chance_drill = INCIDENT_CHANCE_DRILL
        self.hull_critical_pct = HULL_CRITICAL_PCT
        super().__init__(seed=seed, ship_names=ship_names)
        self.stats.setdefault("incidents", 0)
        self.stats.setdefault("ore_mined_t", 0.0)

    # -- construction --------------------------------------------------------
    def _parked_ship(self, name: str, body_key: str) -> Ship:
        ship = super()._parked_ship(name, body_key)
        cls = self._pending_classes.pop(name, DEFAULT_SHIP_CLASS)
        spec = SHIP_CLASSES[cls]
        ship.capacity = spec["capacity"]
        ship.delta_v = spec["delta_v"]
        self.ship_class[name] = cls
        self.hull[name] = HULL_MAX_PCT
        return ship

    # -- fleet management ----------------------------------------------------
    def class_spec(self, ship_name: str) -> dict:
        return SHIP_CLASSES[self.ship_class[ship_name]]

    def buy_ship(self, cls_key: str) -> tuple[Ship | None, str]:
        """Commission a new ship of ``cls_key`` at the colony.

        Payment happens in the game layer; this only validates the class and
        grows the fleet. Returns ``(ship, message)``.
        """
        if cls_key not in SHIP_CLASSES:
            return None, f"Unknown ship class '{cls_key}'."
        name = next((n for n in FLEET_NAME_POOL if n not in self.ship_class), None)
        if name is None:
            return None, "The registry is full; no callsigns remain."
        self._pending_classes[name] = cls_key
        ship = self._parked_ship(name, "colony")
        self.ships.append(ship)
        self.note(f"{name} ({self.class_spec(name)['name']}) commissioned at Colony Hub.")
        return ship, f"{name} ({self.class_spec(name)['name']}) joins the fleet."

    def mining_hull(self, ship: Ship) -> float:
        return self.hull.get(ship.name, HULL_MAX_PCT)

    # -- wear & maintenance --------------------------------------------------
    def _apply_wear(self, ship: Ship, dv_ms: float) -> None:
        if dv_ms <= 0.0:
            return
        factor = self.class_spec(ship.name)["wear_factor"]
        current = self.hull.get(ship.name, HULL_MAX_PCT)
        self.hull[ship.name] = max(HULL_MIN_PCT, current - dv_ms * HULL_WEAR_PCT_PER_MS * factor)

    def refuel_docked_fleet(self, dt_days: float) -> float:
        """Per-class refuel rates; otherwise identical to the base rule."""
        granted = 0.0
        for ship in self.ships:
            if ship.name in self.missions or ship.origin != "colony":
                continue
            full = self.class_spec(ship.name)["delta_v"]
            headroom = full - ship.delta_v
            if headroom <= 0.0:
                continue
            amount = min(headroom, self.class_spec(ship.name)["refuel_rate"] * dt_days)
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
            amount = min(deficit, HULL_REPAIR_RATE_PCT_PER_DAY * dt_days)
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
    def dispatch(self, ship: Ship, target_key: str, cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        if self.hull.get(ship.name, HULL_MAX_PCT) < self.hull_critical_pct:
            return False, (
                f"{ship.name} is worn to {self.hull[ship.name]:.0f}% hull; "
                "repairs are required before dispatch."
            )
        if cargo is None:
            spec = self.class_spec(ship.name)
            payload = plan_extraction(
                target_key,
                self.ledger,
                self.reserved.get(target_key),
                capacity_t=ship.capacity,
                mode=self.mining_mode,
                mine_bonus=spec["mine_bonus"],
                hull_pct=self.mining_hull(ship),
            )
            if sum(payload.values()) < 1.0:
                return False, (
                    f"The veins at {self.bodies[target_key].name} are worked out; "
                    "the field needs years to recover."
                )
            ok, message = super().dispatch(ship, target_key, cargo=payload)
            if ok:
                slot = self.reserved.setdefault(target_key, {})
                for ore, tonnes in payload.items():
                    slot[ore] = slot.get(ore, 0.0) + tonnes
                self._inflight[ship.name] = (target_key, dict(payload))
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

    # -- mission hooks (wear, depletion, incidents) --------------------------
    def _depart(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._depart(ship, mission)
        self._apply_wear(ship, before - ship.delta_v)

    def _capture(self, ship: Ship, mission: Mission, target) -> None:
        inflight = self._inflight.pop(ship.name, None)
        before = ship.delta_v
        super()._capture(ship, mission, target)
        self._apply_wear(ship, before - ship.delta_v)

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

        # Success: draw the vein down and charge drilling wear.
        self.ledger.commit(body_key, payload)
        self.stats["ore_mined_t"] += sum(payload.values())
        if self.mining_mode == "drill":
            self.hull[ship.name] = max(
                HULL_MIN_PCT, self.hull[ship.name] - MINING_DRILL_WEAR_PCT
            )

        # Incident roll: drilling is riskier, a tired hull riskier still.
        chance = self.incident_chance_drill if self.mining_mode == "drill" else self.incident_chance_scrape
        chance += INCIDENT_LOW_HULL_FACTOR * max(0.0, MINING_LOW_HULL_YIELD_PCT - self.hull[ship.name]) / 100.0
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

    def _complete_run(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._complete_run(ship, mission)
        self._apply_wear(ship, before - ship.delta_v)

    # -- reporting -----------------------------------------------------------
    def ship_report(self, ship: Ship) -> dict:
        report = super().ship_report(ship)
        report["class"] = self.ship_class.get(ship.name, DEFAULT_SHIP_CLASS)
        report["hull"] = self.hull.get(ship.name, HULL_MAX_PCT)
        report["capacity"] = ship.capacity
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
            "rng": rng_to_json(self.rng),
            "version": 1,
        }

    @classmethod
    def from_json(cls, data: dict) -> "OpsSimulation":
        sim = cls.__new__(cls)
        sim.time = float(data["time"])
        sim.warp_days_per_second = float(data["warp_days_per_second"])
        sim.bodies = BODIES
        sim.ships = []
        sim.missions = {}
        sim.log = []
        sim._window_cache = {}
        sim._round_trip_cache = {}
        sim._next_scan_time = float(data["next_scan_time"])
        sim.stats = dict(data["stats"])
        sim.pending_deliveries = []
        sim.ship_class = {}
        sim.hull = {}
        # Per-instance knobs normally assigned in __init__; __new__ skips it.
        sim.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        sim.incident_chance_drill = INCIDENT_CHANCE_DRILL
        sim.hull_critical_pct = HULL_CRITICAL_PCT
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
