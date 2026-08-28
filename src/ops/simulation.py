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
* **Crew**: every ship carries a named roster with morale and fatigue.
  Fatigue accumulates in flight and layovers, recovers at the colony; morale
  rises with successful captures and payday, falls with overwork, boredom and
  hardship. Tired or unhappy crews cause incidents and mine less.
* **Space weather**: deterministic solar-flare cycles (quiet -> warning ->
  flare) and periodic debris seasons. Only ships in flight are exposed; both
  add hull wear per day, flares also grind on morale.

The base class remains directly constructible and behaves exactly as before;
every extension here is additive.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

import numpy as np

from src.config import (
    CAMPAIGN_BODIES,
    STATION_MODULE_CATALOG,
    SWARM_BASE_DRONES,
    SWARM_COOLDOWN_DAYS,
    SWARM_CREDIT_COST_PER_DRONE,
    SWARM_DRONES_PER_BAY,
    SWARM_DURATION_DAYS,
    SWARM_ENERGY_COST_PER_DRONE,
    SWARM_MAX_DRONES,
    SWARM_YIELD_T_PER_DRONE_DAY,
    SURFACE_ISRU_DEPOT_GEN_BONUS,
    SURFACE_ISRU_MAX_PER_BODY,
    SURFACE_SURVEY_BONUS,
    SURFACE_SURVEY_DAYS,
    RIVAL_DUMP_PERIOD_DAYS,
    RIVAL_DUMP_TONNES,
    RIVAL_MINE_T_PER_DAY,
    RIVAL_NAME,
    SIM_SECONDS_PER_DAY,
    COMET_ELEMENTS,
    COMET_KEY,
    COMET_VEIN_BONUS,
    CREW_BOTANIST_SAVING_CAP,
    MINING_EXTRA_SPAWNS,
    CREW_BOTANIST_WATER_SAVING,
    DEPOT_BUILD_COST,
    DEPOT_CAPACITY_PER_LEVEL,
    DEPOT_GENERATION_PER_LEVEL,
    DEPOT_START_FUEL,
    DEPOT_UPGRADE_COST,
    DEPOT_UPGRADE_COST_GROWTH,
    CREW_ENGINEER_REPAIR_BONUS,
    CREW_FATIGUE_EXHAUSTED,
    CREW_FIRE_MORALE_HIT,
    CREW_MAX_ROSTER,
    CREW_PILOT_BURN_DISCOUNT,
    CREW_PILOT_DISCOUNT_CAP,
    CREW_FATIGUE_PER_DAY_FLYING,
    CREW_FATIGUE_PER_DAY_LAYOVER,
    CREW_FATIGUE_PER_DAY_PENDING,
    CREW_FATIGUE_RECOVERY_PER_DAY,
    CREW_IDLE_BOREDOM_DAYS,
    CREW_MORALE_BOREDOM_DRAIN_PER_DAY,
    CREW_MORALE_BOREDOM_FLOOR,
    CREW_MORALE_CAPTURE_BONUS,
    CREW_MORALE_CABIN_FEVER_PER_DAY,
    CREW_MORALE_LOW_YIELD,
    CREW_MORALE_MAX,
    CREW_MORALE_OVERWORK_DRAIN_PER_DAY,
    CREW_MORALE_OVERWORK_FLOOR,
    CREW_MORALE_REST_PER_DAY,
    CREW_MORALE_START,
    CREW_NAMES_FIRST,
    CREW_NAMES_LAST,
    DEFAULT_SHIP_CLASS,
    DEBRIS_SEASON_DURATION_DAYS,
    DEBRIS_SEASON_PERIOD_DAYS,
    DEBRIS_WEAR_PCT_PER_DAY,
    FLEET_NAME_POOL,
    FLARE_DURATION_DAYS_RANGE,
    FLARE_MORALE_DRAIN_PER_DAY,
    FLARE_QUIET_DAYS_RANGE,
    FLARE_WARNING_DAYS,
    FLARE_WEAR_PCT_PER_DAY,
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
    MU_SUN,
    PARTS_CATALOG,
    PLANNING_MAX_REVS,
    REFINERY_ARRIVAL_BATCHES,
    REFINERY_BATCHES_PER_DAY,
    REFINERY_BUILD_COST,
    REFINERY_RECIPES,
    PLANNING_MULTI_REV_MIN_SAVING,
    PERTURB_DA_FRACTION,
    PERTURB_DE_MAX,
    PERTURB_MAX_INTERVAL_DAYS,
    PERTURB_MIN_INTERVAL_DAYS,
    SHIP_CLASSES,
    SIM_SECONDS_PER_DAY,
)
from src.market import rng_from_json, rng_to_json
from src.maths.elements import OrbitalElements
from src.maths import windows as window_solver
from src.mining import YieldLedger, plan_extraction, register_body_ores, register_extra_spawns
from src.simulation.bodies import BODIES, Body, TRADE_TARGETS
from src.simulation.orbital_sim import Delivery, Leg, LogEntry, Mission, OrbitalSimulation, Ship


@dataclass
class Depot:
    """A player-built refuel station at a trade body.

    The tank stores propellant measured in delta-v (m/s) -- the same currency
    the ships burn -- and an ISRU plant slowly cracks local ice into more.
    """

    body_key: str
    level: int = 1
    fuel_ms: float = DEPOT_START_FUEL
    #: installed parts: {"drones": n}
    upgrades: dict = field(default_factory=dict)

    @property
    def capacity(self) -> float:
        return DEPOT_CAPACITY_PER_LEVEL * self.level

    @property
    def generation_per_day(self) -> float:
        return DEPOT_GENERATION_PER_LEVEL * self.level

    @property
    def upgrade_cost(self) -> float:
        return DEPOT_UPGRADE_COST * DEPOT_UPGRADE_COST_GROWTH ** (self.level - 1)

    def to_json(self) -> dict:
        return {"body_key": self.body_key, "level": self.level,
                "fuel_ms": self.fuel_ms, "upgrades": dict(self.upgrades)}

    @classmethod
    def from_json(cls, data: dict) -> "Depot":
        return cls(body_key=data["body_key"], level=int(data.get("level", 1)),
                   fuel_ms=float(data.get("fuel_ms", 0.0)),
                   upgrades={k: int(v) for k, v in data.get("upgrades", {}).items()})


@dataclass
class Refinery:
    """A player-built smelting station at a trade body.

    While a ship waits at its body for the return window, the refinery
    converts raw ore in the ship's hold into high-value refined stock
    (components, electronics). Fractional batches accumulate in ``progress``.
    """

    body_key: str
    progress: float = 0.0
    batches_done: int = 0

    def to_json(self) -> dict:
        return {"body_key": self.body_key, "progress": self.progress,
                "batches_done": self.batches_done}

    @classmethod
    def from_json(cls, data: dict) -> "Refinery":
        return cls(body_key=data["body_key"], progress=float(data.get("progress", 0.0)),
                   batches_done=int(data.get("batches_done", 0)))


@dataclass
class CrewMember:
    """One named crew member aboard a colony ship."""

    name: str
    role: str
    morale: float = CREW_MORALE_START
    fatigue: float = 0.0

    def to_json(self) -> dict:
        return {"name": self.name, "role": self.role,
                "morale": self.morale, "fatigue": self.fatigue}

    @classmethod
    def from_json(cls, data: dict) -> "CrewMember":
        return cls(name=data["name"], role=data["role"],
                   morale=float(data["morale"]), fatigue=float(data["fatigue"]))


# Roster template per ship: role -> seats. Miners outnumber everyone because
# mining is where the money (and the incidents) come from.
CREW_ROSTER_TEMPLATE = {"pilot": 1, "miner": 2, "engineer": 1}

# Mission legs that keep a crew away from the colony.
_AWAY_LEGS = {Leg.OUTBOUND, Leg.INBOUND, Leg.WAITING, Leg.PENDING}


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
        #: ship name -> roster of CrewMember
        self.crew: dict[str, list[CrewMember]] = {}
        #: ship name -> installed parts {"tank": n, "drill": n, "quarters": n}
        self.upgrades: dict[str, dict[str, int]] = {}
        #: generic tech multipliers set by the game layer (depot_generation,
        #: refinery, fatigue, hull_wear, refuel_rate) -- the sim never knows
        #: tech or difficulty names, only numbers.
        self.tech_mults: dict[str, float] = {}
        #: hull never drops below this (Ironman can set 0.0 for wrecks)
        self.hull_floor = HULL_MIN_PCT
        #: ship name -> remaining RoutePlan legs (multi-stop delivery)
        self.routes: dict[str, list] = {}
        #: standing auto-dispatch orders (destinations + hop policy)
        self.standing_orders: dict = {"prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}
        #: body_key -> active swarm dict {count, remaining_days, yield_t, launched_day}
        self.swarms: dict[str, dict] = {}
        #: body_key -> sim-day when next swarm is allowed
        self.swarm_cooldown: dict[str, float] = {}
        #: body -> {bonus, expires_day}
        self.survey_bonus: dict[str, dict] = {}
        #: body -> ISRU spike count
        self.isru_spikes: dict[str, int] = {}
        #: body -> {module_key: count}
        self.station_modules: dict[str, dict[str, int]] = {}
        self.rival_enabled = False  # game layer opts in via settings
        self._rival_dump_timer = float(RIVAL_DUMP_PERIOD_DAYS)
        #: body key -> refuel depot (player-built)
        self.depots: dict[str, Depot] = {}
        #: body key -> refinery station (player-built)
        self.refineries: dict[str, Refinery] = {}
        #: the network this campaign flies (extra bodies, e.g. a comet)
        self.trade_targets: tuple[str, ...] = tuple(TRADE_TARGETS)

        #: colony-side botanists (they work the hydroponics racks, not ships)
        self.botanists = 0
        # Gravitational perturbation clock: this sim owns its own body table,
        # so a passing body nudges *this* campaign's orbits and nothing else.
        self._perturb_timer = self.rng.uniform(
            PERTURB_MIN_INTERVAL_DAYS, PERTURB_MAX_INTERVAL_DAYS
        ) * SIM_SECONDS_PER_DAY
        # Multi-rev planning knobs (see config comments).
        self._max_revs = PLANNING_MAX_REVS
        self._multi_rev_min_saving = PLANNING_MULTI_REV_MIN_SAVING
        #: ship name -> sim time of the last departure or docking
        self.last_active: dict[str, float] = {}
        # Space weather state (deterministic, ticked in step()).
        self.flare_state = "quiet"            # quiet | warning | flare
        self._flare_timer = self.rng.uniform(*FLARE_QUIET_DAYS_RANGE) * SIM_SECONDS_PER_DAY
        self._flare_duration = 0.0
        self._debris_timer = DEBRIS_SEASON_PERIOD_DAYS * SIM_SECONDS_PER_DAY
        self.debris_active = False
        # Per-instance knobs so tests can tighten probabilities without
        # touching global config.
        self.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        self.incident_chance_drill = INCIDENT_CHANCE_DRILL
        self.hull_critical_pct = HULL_CRITICAL_PCT
        super().__init__(seed=seed, ship_names=ship_names)
        # Own the body table: perturbations replace entries here instead of
        # mutating the shared module-level BODIES the verified tests read.
        self.bodies = dict(self.bodies)
        self._install_comet()

    def _install_comet(self) -> None:
        """Install campaign-only bodies (comet + deep fields) into this sim copy."""
        self._install_campaign_body_comet()
        self._install_campaign_fields()

    def _install_campaign_body_comet(self) -> None:
        """Add "Vigil", a long-period comet only this campaign can see.

        It lives in the campaign body table; the verified module table stays
        pristine. Called from both ``__init__`` and ``from_json``.
        """
        if COMET_KEY in self.bodies:
            return
        el = OrbitalElements(a=COMET_ELEMENTS["a"], e=COMET_ELEMENTS["e"],
                             i=math.radians(COMET_ELEMENTS["i_deg"]),
                             raan=math.radians(COMET_ELEMENTS["raan_deg"]),
                             argp=math.radians(COMET_ELEMENTS["argp_deg"]),
                             nu=math.radians(COMET_ELEMENTS["nu_deg"]))
        self.bodies[COMET_KEY] = Body(
            key=COMET_KEY, name="Comet Vigil", elements=el,
            radius_km=6.0, soi_km=9000.0,
            palette=(0.72, 0.86, 1.0),
            resources=("ice", "platinum"),
            description="A long-period comet. Rare windows, fast arrival, primordial wealth.",
            render_scale=0.45,
        )
        register_body_ores(COMET_KEY, ("ice", "platinum", "thorite", "aurellium"))
        register_extra_spawns(MINING_EXTRA_SPAWNS)
        if COMET_KEY not in self.trade_targets:
            self.trade_targets = tuple(self.trade_targets) + (COMET_KEY,)
        self.stats.setdefault("incidents", 0)
        self.stats.setdefault("ore_mined_t", 0.0)
        self.stats.setdefault("full_returns", 0)
        self.stats.setdefault("captures_by_body", {})

    # -- construction --------------------------------------------------------
    def _install_campaign_fields(self) -> None:
        """Trojan Field, Cinder Moon, Outer Reach -- multi-hop endgame rocks."""
        for key, spec in CAMPAIGN_BODIES.items():
            if key in self.bodies:
                continue
            el_spec = spec["elements"]
            el = OrbitalElements(
                a=el_spec["a"], e=el_spec["e"],
                i=math.radians(el_spec["i_deg"]),
                raan=math.radians(el_spec["raan_deg"]),
                argp=math.radians(el_spec["argp_deg"]),
                nu=math.radians(el_spec["nu_deg"]),
            )
            self.bodies[key] = Body(
                key=key, name=spec["name"], elements=el,
                radius_km=float(spec["radius_km"]), soi_km=float(spec["soi_km"]),
                palette=tuple(spec["palette"]),
                resources=tuple(spec.get("resources", ())),
                description=str(spec.get("description", "")),
                render_scale=float(spec.get("render_scale", 1.0)),
            )
            register_body_ores(key, tuple(spec.get("resources", ())))
            if key not in self.trade_targets:
                self.trade_targets = tuple(self.trade_targets) + (key,)

    def _parked_ship(self, name: str, body_key: str) -> Ship:
        ship = super()._parked_ship(name, body_key)
        cls = self._pending_classes.pop(name, DEFAULT_SHIP_CLASS)
        spec = SHIP_CLASSES[cls]
        ship.capacity = spec["capacity"]
        ship.delta_v = spec["delta_v"]
        self.ship_class[name] = cls
        self.hull[name] = HULL_MAX_PCT
        self.upgrades[name] = {}
        self._hire_crew(name)
        self.last_active[name] = self.time
        return ship

    def _hire_crew(self, ship_name: str) -> None:
        """Give a ship its roster: deterministic draws from the name pools."""
        roster: list[CrewMember] = []
        for role, seats in CREW_ROSTER_TEMPLATE.items():
            for _ in range(seats):
                name = f"{self.rng.choice(CREW_NAMES_FIRST)} {self.rng.choice(CREW_NAMES_LAST)}"
                roster.append(CrewMember(name=name, role=role))
        self.crew[ship_name] = roster

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

    # -- upgrade parts ---------------------------------------------------------
    def effective_delta_v(self, ship_name: str) -> float:
        """Class budget plus drop tanks."""
        tanks = self.upgrades.get(ship_name, {}).get("tank", 0)
        return self.class_spec(ship_name)["delta_v"] + tanks * PARTS_CATALOG["tank"]["delta_v"]

    def ship_mine_bonus(self, ship_name: str) -> float:
        ups = self.upgrades.get(ship_name, {})
        bonus = 1.0
        for key, count in ups.items():
            bonus += int(count) * float(PARTS_CATALOG.get(key, {}).get("mine_bonus", 0.0) or 0.0)
        bonus *= float(self.tech_mults.get("mine_bonus", 1.0))
        return bonus

    def ship_capacity(self, ship_name: str) -> float:
        spec = self.class_spec(ship_name)
        extra = 0.0
        for key, count in self.upgrades.get(ship_name, {}).items():
            extra += int(count) * float(PARTS_CATALOG.get(key, {}).get("capacity", 0.0) or 0.0)
        return float(spec["capacity"]) + extra

    def body_mine_bonus(self, body_key: str) -> float:
        mods = self.station_modules.get(body_key, {})
        yards = int(mods.get("drill_yard", 0))
        info = STATION_MODULE_CATALOG.get("drill_yard", {})
        return 1.0 + yards * float(info.get("mine_bonus", 0.0))

    def crew_rest_factor(self, ship_name: str) -> float:
        quarters = self.upgrades.get(ship_name, {}).get("quarters", 0)
        return 1.0 + quarters * PARTS_CATALOG["quarters"]["rest_bonus"]

    def install_part(self, ship_name: str, part_key: str) -> tuple[bool, str]:
        info = PARTS_CATALOG.get(part_key)
        if info is None or part_key == "drones":
            return False, "That is not a ship part."
        owned = self.upgrades.setdefault(ship_name, {})
        if owned.get(part_key, 0) >= info["max_per_ship"]:
            return False, f"{ship_name} already carries the maximum {info['name']}s."
        owned[part_key] = owned.get(part_key, 0) + 1
        if float(info.get("capacity", 0.0) or 0.0) > 0.0:
            for ship in self.ships:
                if ship.name == ship_name:
                    ship.capacity = self.ship_capacity(ship_name)
                    break
        return True, f"{info['name']} installed on {ship_name}."

    def install_depot_part(self, body_key: str, part_key: str) -> tuple[bool, str]:
        depot = self.depots.get(body_key)
        if depot is None:
            return False, "Build a depot there first."
        info = PARTS_CATALOG.get(part_key)
        if info is None or part_key != "drones":
            return False, "That is not a depot part."
        owned = depot.upgrades.setdefault(part_key, 0)
        if owned >= info["max_per_depot"]:
            return False, f"The {self.bodies[body_key].name} depot is at its drone-bay limit."
        depot.upgrades[part_key] = owned + 1
        return True, f"Drone bay online at the {self.bodies[body_key].name} depot."

    # -- wear & maintenance --------------------------------------------------
    def _apply_wear(self, ship: Ship, dv_ms: float) -> None:
        if dv_ms <= 0.0:
            return
        factor = self.class_spec(ship.name)["wear_factor"]
        # Difficulty (and future techs) scale wear via a generic multiplier.
        factor *= float(self.tech_mults.get("hull_wear", 1.0))
        for key, count in self.upgrades.get(ship.name, {}).items():
            wf = PARTS_CATALOG.get(key, {}).get("wear_factor")
            if wf and int(count) > 0:
                factor *= float(wf) ** int(count)
        current = self.hull.get(ship.name, HULL_MAX_PCT)
        floor = float(getattr(self, "hull_floor", HULL_MIN_PCT))
        self.hull[ship.name] = max(floor, current - dv_ms * HULL_WEAR_PCT_PER_MS * factor)

    def affordable_targets(self, ship: Ship, margin: float = 1.15) -> list[tuple[str, float]]:
        """Campaign-network override of the base affordability scan."""
        affordable: list[tuple[str, float]] = []
        for key in self.trade_targets:
            if key == ship.origin:
                continue
            cost = self.round_trip_cost_ms(ship.origin, key)
            if cost is not None and cost * margin <= ship.delta_v:
                affordable.append((key, cost))
        affordable.sort(key=lambda item: item[1])
        return affordable

    def refuel_docked_fleet(self, dt_days: float) -> float:
        """Per-class refuel rates; otherwise identical to the base rule."""
        granted = 0.0
        for ship in self.ships:
            if ship.name in self.missions or ship.origin != "colony":
                continue
            full = self.effective_delta_v(ship.name)
            headroom = full - ship.delta_v
            if headroom <= 0.0:
                continue
            rate = self.class_spec(ship.name)["refuel_rate"] * float(
                self.tech_mults.get("refuel_rate", 1.0))
            amount = min(headroom, rate * dt_days)
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
            rate = HULL_REPAIR_RATE_PCT_PER_DAY
            if self.has_engineer(ship.name):
                rate *= 1.0 + CREW_ENGINEER_REPAIR_BONUS
            amount = min(deficit, rate * dt_days)
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
    def _depot_bond(self, ship: Ship, target_key: str) -> float:
        """Delta-v loan a depot at ``target_key`` can back, or 0.

        Conditions: the ship can reach the target on its own tank (outbound
        window total fits), and the depot tank holds enough to cover the ride
        home that the ship cannot pay for itself.
        """
        depot = self.depots.get(target_key)
        if depot is None:
            return 0.0
        outbound = self.launch_window(ship.origin, target_key)
        if outbound is None:
            return 0.0
        _, return_window = self.plan_round_trip(ship.origin, target_key, max_age=None)
        if return_window is None:
            return 0.0
        out_cost = self.delta_v_km_s(outbound.total_delta_v) * 1000.0
        back_cost = self.delta_v_km_s(return_window.total_delta_v) * 1000.0
        if out_cost > ship.delta_v:
            return 0.0
        shortfall = back_cost - (ship.delta_v - out_cost)
        if shortfall <= 0.0:
            return 0.0
        if depot.fuel_ms < shortfall:
            return 0.0
        return shortfall

    def dispatch(self, ship: Ship, target_key: str, cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        if self.hull.get(ship.name, HULL_MAX_PCT) < self.hull_critical_pct:
            return False, (
                f"{ship.name} is worn to {self.hull[ship.name]:.0f}% hull; "
                "repairs are required before dispatch."
            )
        morale, fatigue = self.crew_stats(ship.name)
        if fatigue > CREW_FATIGUE_EXHAUSTED:
            who = max(self.crew[ship.name], key=lambda member: member.fatigue).name
            return False, (
                f"{ship.name}'s crew is exhausted ({who} at {fatigue:.0f}% fatigue); "
                "they need dock time before another run."
            )
        if cargo is None:
            spec = self.class_spec(ship.name)
            payload = plan_extraction(
                target_key,
                self.ledger,
                self.reserved.get(target_key),
                capacity_t=self.ship_capacity(ship.name),
                mode=self.mining_mode,
                mine_bonus=spec["mine_bonus"] * self.crew_yield_factor(ship.name)
                * self.ship_mine_bonus(ship.name) * self.survey_mult(target_key)
                * self.body_mine_bonus(target_key),
                hull_pct=self.mining_hull(ship),
            )
            if sum(payload.values()) < 1.0:
                return False, (
                    f"The veins at {self.bodies[target_key].name} are worked out; "
                    "the field needs years to recover."
                )
            bond = self._depot_bond(ship, target_key)
            if bond > 0.0:
                # Depot-assisted run: lend the ship the delta-v it will be
                # granted at the depot so the round-trip check passes, then
                # take the loan back -- the ride home comes from the depot
                # tank while the ship waits for the return window.
                ship.delta_v += bond
                try:
                    ok, message = super().dispatch(ship, target_key, cargo=payload)
                finally:
                    ship.delta_v -= bond
                if ok:
                    depot = self.depots[target_key]
                    self.note(
                        f"{ship.name} plans a depot-supported run to "
                        f"{self.bodies[target_key].name} "
                        f"({depot.fuel_ms:,.0f} m/s in the tank)."
                    )
                    slot = self.reserved.setdefault(target_key, {})
                    for ore, tonnes in payload.items():
                        slot[ore] = slot.get(ore, 0.0) + tonnes
                    self._inflight[ship.name] = (target_key, dict(payload))
                return ok, message
            ok, message = super().dispatch(ship, target_key, cargo=payload)
            if ok:
                slot = self.reserved.setdefault(target_key, {})
                for ore, tonnes in payload.items():
                    slot[ore] = slot.get(ore, 0.0) + tonnes
                self._inflight[ship.name] = (target_key, dict(payload))
                mission = self.missions.get(ship.name)
                if mission is not None and mission.return_window is not None:
                    revs = max(getattr(mission.return_window, "revs", 0), 0)
                    if revs >= 1:
                        self.note(
                            f"{ship.name} flies a {revs}-revolution slow route "
                            f"(propellant over pace)."
                        )
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


    # -- multi-stop delivery planner -------------------------------------------
    def plan_delivery(self, ship: Ship, target_key: str, prefer_hops: bool | None = None):
        """Return the best RoutePlan for ``ship`` → ``target_key`` (or None)."""
        from src.routes import plan_route
        if prefer_hops is None:
            prefer_hops = bool(self.standing_orders.get("prefer_hops", True))
        return plan_route(self, ship, target_key, prefer_hops=prefer_hops)

    def dispatch_route(self, ship: Ship, target_key: str,
                       cargo: dict[str, float] | None = None) -> tuple[bool, str]:
        """Dispatch using the multi-stop planner when a direct run will not fit.

        Direct-capable runs still go through the normal single-leg dispatch.
        Otherwise the first hop is flown now and the remaining legs are queued
        on ``self.routes[ship.name]``; each completed hop auto-continues.
        """
        from src.routes import plan_route, route_preview_lines

        if ship.name in self.missions:
            return False, f"{ship.name} is already flying a mission."
        plan = plan_route(self, ship, target_key)
        if plan is None:
            return False, f"No route to {self.bodies.get(target_key, target_key)}."
        if plan.direct or plan.hop_count == 0:
            return self.dispatch(ship, target_key, cargo=cargo)

        # Multi-hop: fly the first leg; queue the rest.
        first = plan.legs[0]
        if first.purpose == "harvest":
            ok, message = self.dispatch(ship, first.destination, cargo=cargo)
        else:
            # Pure transfer / refuel hop: fly empty so veins are not reserved.
            ok, message = super().dispatch(ship, first.destination, cargo={"ice": 0.01})
            if ok:
                ship.cargo = {}
                mission = self.missions.get(ship.name)
                if mission is not None:
                    mission.cargo = {}
                self._inflight.pop(ship.name, None)
        if not ok:
            return False, message
        # Stash remaining legs (after the one just started).
        remaining = list(plan.legs[1:])
        self.routes[ship.name] = remaining
        via = "/".join(self.bodies[k].name if k in self.bodies else k for k in plan.via)
        self.note(
            f"{ship.name} flies a multi-stop harvest to "
            f"{self.bodies[target_key].name} via {via} "
            f"({plan.hop_count} hop(s), {plan.total_ms:,.0f} m/s billed)."
        )
        preview = route_preview_lines(plan, self.bodies)
        return True, f"{ship.name} multi-stop: {preview[1]}"

    def _continue_route(self, ship: Ship) -> None:
        """After a hop completes, launch the next queued leg if any."""
        queue = self.routes.get(ship.name) or []
        if not queue:
            self.routes.pop(ship.name, None)
            return
        if ship.name in self.missions:
            return
        nxt = queue.pop(0)
        self.routes[ship.name] = queue
        purpose = nxt.purpose
        dest = nxt.destination
        # Top up from a depot if we are sitting on one.
        depot = self.depots.get(ship.origin)
        if depot is not None:
            full = self.effective_delta_v(ship.name)
            headroom = full - ship.delta_v
            draw = min(headroom, depot.fuel_ms)
            if draw > 1.0:
                ship.delta_v += draw
                depot.fuel_ms -= draw
                self.note(
                    f"{ship.name} tops up at {self.bodies[ship.origin].name} "
                    f"depot (+{draw:,.0f} m/s) before the next hop."
                )
        cargo = None
        if purpose == "harvest":
            cargo = None  # let dispatch plan extraction
            ok, message = self.dispatch(ship, dest, cargo=None)
        else:
            ok, message = super().dispatch(ship, dest, cargo={"ice": 0.0})
            if ok:
                ship.cargo = {}
                mission = self.missions.get(ship.name)
                if mission is not None:
                    mission.cargo = {}
                self._inflight.pop(ship.name, None)
        if ok:
            self.note(f"{ship.name} continues route: {purpose} → {self.bodies.get(dest, dest).name if dest in self.bodies else dest}.")
        else:
            self.note(f"{ship.name} route stalled at {ship.origin}: {message}")
            self.routes.pop(ship.name, None)



    def plant_survey(self, body_key: str) -> tuple[bool, str]:
        """Chart veins on a body: temporary extraction bonus."""
        if body_key not in self.bodies or body_key == "colony":
            return False, "Survey a harvest field."
        day = self.time / SIM_SECONDS_PER_DAY
        self.survey_bonus[body_key] = {
            "bonus": float(SURFACE_SURVEY_BONUS),
            "expires_day": day + float(SURFACE_SURVEY_DAYS),
        }
        self.stats["surveys"] = int(self.stats.get("surveys", 0)) + 1
        self.note(
            f"Surface survey complete at {self.bodies[body_key].name}: "
            f"+{SURFACE_SURVEY_BONUS*100:.0f}% yield for {SURFACE_SURVEY_DAYS:.0f} d."
        )
        return True, (
            f"{self.bodies[body_key].name} surveyed — "
            f"+{SURFACE_SURVEY_BONUS*100:.0f}% harvest for {SURFACE_SURVEY_DAYS:.0f} d."
        )

    def plant_isru_spike(self, body_key: str) -> tuple[bool, str]:
        """Permanent depot-generation boost on this body (needs/creates barn synergy)."""
        if body_key not in self.bodies or body_key == "colony":
            return False, "Plant the spike on a harvest field."
        owned = int(self.isru_spikes.get(body_key, 0))
        if owned >= SURFACE_ISRU_MAX_PER_BODY:
            return False, f"{self.bodies[body_key].name} already has {owned} ISRU spikes."
        self.isru_spikes[body_key] = owned + 1
        self.stats["isru_spikes"] = int(self.stats.get("isru_spikes", 0)) + 1
        self.note(
            f"ISRU spike planted at {self.bodies[body_key].name} "
            f"(+{SURFACE_ISRU_DEPOT_GEN_BONUS:.1f} m/s/day when a barn is online)."
        )
        return True, (
            f"ISRU spike #{owned+1} online at {self.bodies[body_key].name}."
        )

    def survey_mult(self, body_key: str) -> float:
        info = self.survey_bonus.get(body_key)
        if not info:
            return 1.0
        day = self.time / SIM_SECONDS_PER_DAY
        if day > float(info.get("expires_day", 0.0)):
            self.survey_bonus.pop(body_key, None)
            return 1.0
        return 1.0 + float(info.get("bonus", 0.0))

    def tick_rival(self, dt_days: float) -> None:
        """Competing charter quietly mines veins and dumps on Earth occasionally."""
        if not getattr(self, "rival_enabled", True) or dt_days <= 0.0:
            return
        targets = [k for k in self.trade_targets if k in self.bodies]
        if not targets:
            return
        # Deterministic pick from RNG already on the sim.
        key = self.rng.choice(sorted(targets))
        pull = float(RIVAL_MINE_T_PER_DAY) * dt_days
        try:
            from src.mining import plan_extraction
            payload = plan_extraction(
                key, self.ledger, self.reserved.get(key),
                capacity_t=pull, mode="scrape", mine_bonus=0.7, hull_pct=100.0,
            )
        except Exception:
            payload = {}
        if payload:
            self.ledger.commit(key, payload)
            self.stats["rival_mined_t"] = float(self.stats.get("rival_mined_t", 0.0)) + sum(payload.values())
        self._rival_dump_timer = float(getattr(self, "_rival_dump_timer", RIVAL_DUMP_PERIOD_DAYS)) - dt_days
        if self._rival_dump_timer <= 0.0:
            self._rival_dump_timer = float(RIVAL_DUMP_PERIOD_DAYS) * self.rng.uniform(0.8, 1.3)
            # Signal the game layer via stats flag; market dump applied there.
            self.stats["rival_dump_pending"] = 1

    def build_station_module(self, body_key: str, module_key: str) -> tuple[bool, str]:
        """Install a body-side industry module (caller pays credits)."""
        info = STATION_MODULE_CATALOG.get(module_key)
        if info is None:
            return False, f"Unknown station module '{module_key}'."
        if body_key not in self.bodies or body_key == "colony":
            return False, "Build modules on a harvest field."
        owned = int(self.station_modules.setdefault(body_key, {}).get(module_key, 0))
        if owned >= int(info.get("max_per_body", 1)):
            return False, f"{self.bodies[body_key].name} already has max {info['name']}."
        self.station_modules[body_key][module_key] = owned + 1
        self.stats["modules_built"] = int(self.stats.get("modules_built", 0)) + 1
        self.note(f"{info['name']} online at {self.bodies[body_key].name}.")
        return True, f"{info['name']} online at {self.bodies[body_key].name}."

    def body_weather_resist(self, body_key: str) -> float:
        """0..1 fraction of flare/debris wear blocked while WAITING here."""
        masts = int(self.station_modules.get(body_key, {}).get("shield_mast", 0))
        if not masts:
            return 0.0
        return min(0.9, masts * float(STATION_MODULE_CATALOG["shield_mast"].get("weather_resist", 0.5)))

    def tick_observatories(self, dt_days: float) -> float:
        """Passive research from any station module that lists research_per_day."""
        total = 0.0
        for mods in self.station_modules.values():
            for key, count in mods.items():
                rate = float(STATION_MODULE_CATALOG.get(key, {}).get("research_per_day", 0.0) or 0.0)
                n = int(count)
                if rate and n:
                    total += rate * n * dt_days
        return total

    def tick_garden_ice(self, dt_days: float) -> float:
        """Ice tonnes greenhouse domes want to drink this step (caller bills storage)."""
        if dt_days <= 0.0:
            return 0.0
        per = float(STATION_MODULE_CATALOG.get("greenhouse", {}).get("garden_ice_per_day", 0.0) or 0.0)
        count = 0
        for mods in self.station_modules.values():
            count += int(mods.get("greenhouse", 0))
        return per * count * dt_days

    def warehouse_storage_bonus(self) -> float:
        total = 0.0
        per = float(STATION_MODULE_CATALOG.get("warehouse", {}).get("storage_bonus", 0.0))
        for mods in self.station_modules.values():
            total += per * int(mods.get("warehouse", 0))
        return total

    # -- harvest drone swarms (window GO moment) --------------------------------
    def total_drone_bays(self) -> int:
        return sum(int(d.upgrades.get("drones", 0)) for d in self.depots.values())

    def swarm_capacity(self) -> int:
        bays = max(0, self.total_drone_bays())
        return int(min(SWARM_MAX_DRONES, SWARM_BASE_DRONES + SWARM_DRONES_PER_BAY * bays))

    def launch_swarm(self, body_key: str) -> tuple[bool, str, int]:
        """Flood a field with harvest drones while its window is open.

        Returns (ok, message, drone_count). Caller bills credits/energy.
        """
        if body_key not in self.bodies or body_key == "colony":
            return False, "Pick a harvest field.", 0
        if body_key in self.swarms:
            return False, f"A swarm is already working {self.bodies[body_key].name}.", 0
        now_day = self.time / SIM_SECONDS_PER_DAY
        ready = self.swarm_cooldown.get(body_key, -1e9)
        if now_day < ready:
            return False, (
                f"Swarm systems cooling down at {self.bodies[body_key].name} "
                f"({ready - now_day:,.0f} d left)."
            ), 0
        # Window must be open (or about to open within a day).
        window = self.launch_window("colony", body_key)
        if window is None:
            return False, f"No launch window to {self.bodies[body_key].name}.", 0
        wait = (window.departure_time - self.time) / SIM_SECONDS_PER_DAY
        if wait > 1.0:
            return False, (
                f"Window to {self.bodies[body_key].name} opens in {wait:,.0f} d -- "
                "swarm launches only on GO."
            ), 0
        count = self.swarm_capacity()
        if count < 4:
            return False, "Build depot drone bays (P) before launching a swarm.", 0
        self.swarms[body_key] = {
            "count": count,
            "remaining_days": float(SWARM_DURATION_DAYS),
            "yield_t": 0.0,
            "launched_day": now_day,
        }
        self.swarm_cooldown[body_key] = now_day + SWARM_COOLDOWN_DAYS
        self.stats["swarms_launched"] = int(self.stats.get("swarms_launched", 0)) + 1
        self.stats["swarm_drones_peak"] = max(
            int(self.stats.get("swarm_drones_peak", 0)), count)
        self.note(
            f"SWARM LAUNCH: {count} harvest drones dive on {self.bodies[body_key].name} "
            f"(window GO, {SWARM_DURATION_DAYS:.0f} d burst)."
        )
        return True, (
            f"{count} drones inbound to {self.bodies[body_key].name} -- "
            f"harvest window {SWARM_DURATION_DAYS:.0f} d."
        ), count

    def tick_swarms(self, dt_days: float) -> list[dict]:
        """Advance active swarms; return list of finished {body, yield_t, count}."""
        finished = []
        if dt_days <= 0.0 or not self.swarms:
            return finished
        for key in list(self.swarms):
            swarm = self.swarms[key]
            count = int(swarm["count"])
            # Ore pull into a virtual hold then committed via ledger-aware plan.
            swarm_mult = float(self.tech_mults.get("swarm_yield", 1.0))
            pull = count * SWARM_YIELD_T_PER_DRONE_DAY * swarm_mult * dt_days
            try:
                from src.mining import plan_extraction
                payload = plan_extraction(
                    key, self.ledger, self.reserved.get(key),
                    capacity_t=pull, mode=self.mining_mode,
                    mine_bonus=(1.0 + 0.05 * self.total_drone_bays()) * self.survey_mult(key),
                    hull_pct=100.0,
                )
            except Exception:
                payload = {"ice": pull * 0.5, "iron": pull * 0.5}
            if payload:
                self.ledger.commit(key, payload)
                tonnes = float(sum(payload.values()))
                swarm["yield_t"] = float(swarm.get("yield_t", 0.0)) + tonnes
                self.stats["ore_mined_t"] = float(self.stats.get("ore_mined_t", 0.0)) + tonnes
                # Stage as a pending delivery into the colony.
                self.pending_deliveries.append(
                    Delivery(ship=f"swarm:{key}", body=key, time=self.time, cargo=dict(payload))
                )
            swarm["remaining_days"] = float(swarm["remaining_days"]) - dt_days
            if swarm["remaining_days"] <= 0.0:
                finished.append({
                    "body": key,
                    "yield_t": float(swarm.get("yield_t", 0.0)),
                    "count": count,
                })
                self.note(
                    f"Swarm over {self.bodies[key].name} recovered: "
                    f"{swarm.get('yield_t', 0.0):,.0f} t hauled by {count} drones."
                )
                del self.swarms[key]
        return finished

    # -- refuel depots ---------------------------------------------------------
    def build_depot(self, body_key: str) -> tuple[bool, str]:
        """Raise a depot at ``body_key`` (caller pays the credits)."""
        if body_key not in self.trade_targets and body_key not in TRADE_TARGETS:
            return False, "Pick a trade body to build at."
        if body_key in self.depots:
            depot = self.depots[body_key]
            depot.level += 1
            self.note(f"Depot at {self.bodies[body_key].name} upgraded to level {depot.level}.")
            return True, (f"Depot upgraded to level {depot.level} "
                          f"(+{DEPOT_GENERATION_PER_LEVEL:.0f} m/s per day).")
        self.depots[body_key] = Depot(body_key=body_key)
        self.note(f"Refuel depot online at {self.bodies[body_key].name}.")
        return True, f"Depot online at {self.bodies[body_key].name}."

    def depot_upgrade_cost(self, body_key: str) -> float:
        depot = self.depots.get(body_key)
        if depot is None:
            return DEPOT_BUILD_COST
        return depot.upgrade_cost

    # -- refinery stations -------------------------------------------------------
    def build_refinery(self, body_key: str) -> tuple[bool, str]:
        """Raise a smelting station at ``body_key`` (caller pays the credits)."""
        if body_key not in self.trade_targets:
            return False, "Pick a trade body to build at."
        if body_key in self.refineries:
            return False, f"A refinery already operates at {self.bodies[body_key].name}."
        self.refineries[body_key] = Refinery(body_key=body_key)
        self.note(f"Refinery online at {self.bodies[body_key].name}.")
        return True, f"Refinery online at {self.bodies[body_key].name}."

    def refinery_upgrade_cost(self, body_key: str) -> float:
        return REFINERY_BUILD_COST if body_key not in self.refineries else 0.0

    def _refinery_smelt_waiting(self, dt_days: float) -> int:
        """Smelt raw ore in waiting ships' holds; returns batches executed."""
        if dt_days <= 0.0 or not self.refineries:
            return 0
        batches = 0
        for ship in self.ships:
            mission = self.missions.get(ship.name)
            if mission is None or mission.leg is not Leg.WAITING:
                continue
            refinery = self.refineries.get(mission.target)
            if refinery is None:
                continue
            foundry = int(self.station_modules.get(mission.target, {}).get("foundry", 0))
            foundry_mult = 1.0 + foundry * float(
                STATION_MODULE_CATALOG.get("foundry", {}).get("refinery_bonus", 0.0) or 0.0)
            refinery.progress += (
                REFINERY_BATCHES_PER_DAY * self.tech_mults.get("refinery", 1.0) * foundry_mult * dt_days
            )
            while refinery.progress >= 1.0:
                recipe = self._first_craftable_recipe(ship)
                if recipe is None:
                    refinery.progress = min(refinery.progress, 1.0)  # idle: never bank up
                    break
                refinery.progress -= 1.0
                refinery.batches_done += 1
                batches += 1
                for ore, amount in recipe["input"].items():
                    ship.cargo[ore] = ship.cargo.get(ore, 0.0) - amount
                ship.cargo[recipe["output"]] = ship.cargo.get(recipe["output"], 0.0) + recipe["amount"]
        return batches

    @staticmethod
    def _first_craftable_recipe(ship: Ship):
        for recipe in REFINERY_RECIPES:
            if all(ship.cargo.get(ore, 0.0) >= amount for ore, amount in recipe["input"].items()):
                return recipe
        return None

    def tick_depots(self, dt_days: float) -> None:
        """ISRU plants crack local ice into propellant."""
        if dt_days <= 0.0:
            return
        gen_mult = self.tech_mults.get("depot_generation", 1.0)
        for depot in self.depots.values():
            spikes = int(self.isru_spikes.get(depot.body_key, 0))
            extra = spikes * SURFACE_ISRU_DEPOT_GEN_BONUS
            gen = (depot.generation_per_day + extra) * gen_mult
            depot.fuel_ms = min(depot.capacity, depot.fuel_ms + gen * dt_days)

    def _tanker_fill_depot(self, dt_days: float) -> float:
        """Tankers waiting at a barn pump propellant into the tank (logistics loop)."""
        filled = 0.0
        for ship in self.ships:
            if self.ship_class.get(ship.name) != "tanker":
                continue
            mission = self.missions.get(ship.name)
            if mission is None or mission.leg.value != "waiting":
                continue
            depot = self.depots.get(mission.target)
            if depot is None:
                continue
            bonus = float(self.class_spec(ship.name).get("depot_fill_bonus", 1.0))
            # Generate into depot from "tanker ISRU assist" using ship refuel rate * bonus.
            rate = self.class_spec(ship.name)["refuel_rate"] * bonus * float(
                self.tech_mults.get("refuel_rate", 1.0))
            room = depot.capacity - depot.fuel_ms
            add = min(room, rate * dt_days)
            if add > 0.0:
                depot.fuel_ms += add
                filled += add
        return filled

    def _depot_refuel_waiting(self, dt_days: float) -> float:
        """Top up ships holding at a depot body; returns m/s transferred."""
        granted = 0.0
        for ship in self.ships:
            mission = self.missions.get(ship.name)
            if mission is None or mission.leg is not Leg.WAITING:
                continue
            depot = self.depots.get(mission.target)
            if depot is None:
                continue
            headroom = self.class_spec(ship.name)["delta_v"] - ship.delta_v
            if headroom <= 0.0:
                continue
            rate = self.class_spec(ship.name)["refuel_rate"] * float(
                self.tech_mults.get("refuel_rate", 1.0))
            draw = min(headroom, depot.fuel_ms, rate * dt_days)
            if draw <= 0.0:
                continue
            ship.delta_v += draw
            depot.fuel_ms -= draw
            granted += draw
        return granted

    def _depot_drones_load(self, dt_days: float) -> None:
        """Drone bays mine the local field into a waiting ship's hold.

        Physically coherent idle income: while the crew holds for the return
        window, the depot's drones keep hauling ore up, so the ship leaves
        FULL instead of empty. Ore comes from the same depletion ledgers as
        everything else -- strong, but not free.
        """
        if dt_days <= 0.0:
            return
        for ship in self.ships:
            mission = self.missions.get(ship.name)
            if mission is None or mission.leg is not Leg.WAITING:
                continue
            depot = self.depots.get(mission.target)
            drone_levels = depot.upgrades.get("drones", 0) if depot else 0
            if drone_levels <= 0:
                continue
            free = ship.capacity - ship.cargo_load
            if free <= 0.5:
                continue
            tonnes = min(free, PARTS_CATALOG["drones"]["mine_per_day"] * drone_levels * dt_days)
            payload = plan_extraction(
                mission.target, self.ledger, None,
                capacity_t=tonnes, mode="scrape",
                mine_bonus=self.ship_mine_bonus(ship.name),
                hull_pct=self.mining_hull(ship),
            )
            if sum(payload.values()) <= 0.05:
                continue
            self.ledger.commit(mission.target, payload)
            for ore, amount in payload.items():
                ship.cargo[ore] = ship.cargo.get(ore, 0.0) + amount

    # -- crew ----------------------------------------------------------------
    def crew_stats(self, ship_name: str) -> tuple[float, float]:
        """``(average morale, max fatigue)`` across a ship's roster."""
        roster = self.crew.get(ship_name)
        if not roster:
            return CREW_MORALE_START, 0.0
        morale = sum(member.morale for member in roster) / len(roster)
        fatigue = max(member.fatigue for member in roster)
        return morale, fatigue

    def crew_yield_factor(self, ship_name: str) -> float:
        """Unhappy or exhausted crews mine less (multiplicative, in (0, 1])."""
        morale, fatigue = self.crew_stats(ship_name)
        factor = 0.85 + 0.15 * morale / CREW_MORALE_MAX
        if fatigue > 70.0:
            factor *= 0.9
        return factor

    def crew_incident_factor(self, ship_name: str) -> float:
        """Tired crews crash drills; sullen crews get careless (>= 1)."""
        morale, fatigue = self.crew_stats(ship_name)
        return 1.0 + max(0.0, fatigue - 60.0) / 100.0 + max(0.0, CREW_MORALE_LOW_YIELD - morale) / 100.0

    def tick_crew(self, dt_days: float) -> None:
        """Advance fatigue and morale for every roster by ``dt_days``."""
        if dt_days <= 0.0:
            return
        for ship in self.ships:
            roster = self.crew.get(ship.name)
            if not roster:
                continue
            mission = self.missions.get(ship.name)
            if mission is None:
                # Docked: fatigue recovers. A crew with nothing to do for
                # months slowly gets bored.
                bored = (
                    self.time - self.last_active.get(ship.name, self.time)
                    > CREW_IDLE_BOREDOM_DAYS * SIM_SECONDS_PER_DAY
                )
                rest_rate = CREW_FATIGUE_RECOVERY_PER_DAY * self.crew_rest_factor(ship.name)
                for member in roster:
                    member.fatigue = max(0.0, member.fatigue - rest_rate * dt_days)
                    if bored and member.fatigue < 30.0:
                        member.morale = max(
                            CREW_MORALE_BOREDOM_FLOOR,
                            member.morale - CREW_MORALE_BOREDOM_DRAIN_PER_DAY * dt_days,
                        )
                    else:
                        member.morale = min(CREW_MORALE_MAX, member.morale + CREW_MORALE_REST_PER_DAY * dt_days)
            else:
                fatigue_mult = self.tech_mults.get("fatigue", 1.0)
                if mission.leg is Leg.WAITING:
                    rate = CREW_FATIGUE_PER_DAY_LAYOVER * fatigue_mult
                elif mission.leg is Leg.PENDING:
                    rate = CREW_FATIGUE_PER_DAY_PENDING * fatigue_mult
                else:
                    rate = CREW_FATIGUE_PER_DAY_FLYING * fatigue_mult
                for member in roster:
                    member.fatigue = min(100.0, member.fatigue + rate * dt_days)
                    if member.fatigue > 70.0:
                        member.morale = max(
                            CREW_MORALE_OVERWORK_FLOOR,
                            member.morale - CREW_MORALE_OVERWORK_DRAIN_PER_DAY * dt_days,
                        )
                if mission.leg is Leg.WAITING:
                    for member in roster:
                        member.morale -= CREW_MORALE_CABIN_FEVER_PER_DAY * dt_days
                if self.flare_state == "flare" and mission.leg in (Leg.OUTBOUND, Leg.INBOUND):
                    for member in roster:
                        member.morale -= FLARE_MORALE_DRAIN_PER_DAY * dt_days
            for member in roster:
                member.morale = min(CREW_MORALE_MAX, max(0.0, member.morale))

    def crew_payday(self, bonus: float = CREW_MORALE_CAPTURE_BONUS) -> None:
        """A little pride (and cash) for everyone; called on sales by the game."""
        for roster in self.crew.values():
            for member in roster:
                member.morale = min(CREW_MORALE_MAX, member.morale + bonus)

    # -- crew specialisations -----------------------------------------------
    def pilots_discount(self, ship_name: str) -> float:
        """Fraction of every burn refunded by planning skill (ops-layer):
        pilots fly tighter courses, Navigation Suites plan them better."""
        count = sum(1 for member in self.crew.get(ship_name, []) if member.role == "pilot")
        suites = self.upgrades.get(ship_name, {}).get("navsuite", 0)
        suite_refund = suites * PARTS_CATALOG["navsuite"]["refund"]
        return min(CREW_PILOT_DISCOUNT_CAP + suite_refund,
                   count * CREW_PILOT_BURN_DISCOUNT + suite_refund)

    def has_engineer(self, ship_name: str) -> bool:
        return any(member.role == "engineer" for member in self.crew.get(ship_name, []))

    def botanist_water_factor(self) -> float:
        """Hydroponics water multiplier from the colony's botanists."""
        return 1.0 - min(CREW_BOTANIST_SAVING_CAP, self.botanists * CREW_BOTANIST_WATER_SAVING)

    def hire(self, role: str, ship_name: str | None = None) -> tuple[bool, str]:
        """Hire a specialist. Botanists join the colony, others a ship."""
        if role == "botanist":
            self.botanists += 1
            self.note(f"A botanist joins the colony hydroponics roster.")
            return True, "Botanist hired for the colony."
        if ship_name is None or ship_name not in self.crew:
            return False, "Pick a ship for the new hire."
        roster = self.crew[ship_name]
        if len(roster) >= CREW_MAX_ROSTER:
            return False, f"{ship_name}'s roster is full ({CREW_MAX_ROSTER} bunks)."
        name = f"{self.rng.choice(CREW_NAMES_FIRST)} {self.rng.choice(CREW_NAMES_LAST)}"
        roster.append(CrewMember(name=name, role=role))
        self.note(f"{name} signs on aboard {ship_name} as {role}.")
        return True, f"{name} joins {ship_name} as {role}."

    def fire(self, ship_name: str, member: CrewMember) -> tuple[bool, str]:
        """Dismiss a crew member; the survivors resent it."""
        roster = self.crew.get(ship_name, [])
        if member not in roster or len(roster) <= 1:
            return False, "Cannot dismiss the last crew member."
        roster.remove(member)
        for other in roster:
            other.morale = max(0.0, other.morale - CREW_FIRE_MORALE_HIT)
        self.note(f"{member.name} is dismissed from {ship_name}; morale suffers.")
        return True, f"{member.name} dismissed; {ship_name}'s crew morale drops."

    def apply_hardship(self, amount: float) -> None:
        """Colony-wide morale damage (life-support shortages, disasters)."""
        for roster in self.crew.values():
            for member in roster:
                member.morale = max(0.0, member.morale - amount)

    def fleet_morale(self) -> float:
        values = [member.morale for roster in self.crew.values() for member in roster]
        return sum(values) / len(values) if values else CREW_MORALE_START

    # -- space weather ---------------------------------------------------------
    def tick_weather(self, dt_days: float) -> None:
        """Advance the deterministic flare cycle and debris seasons."""
        if dt_days <= 0.0:
            return
        dt = dt_days * SIM_SECONDS_PER_DAY
        self._flare_timer -= dt
        if self.flare_state == "quiet" and self._flare_timer <= 0.0:
            self.flare_state = "warning"
            self._flare_timer = FLARE_WARNING_DAYS * SIM_SECONDS_PER_DAY
            self.note("Solar observatory: flare inbound. Ships in flight are exposed.")
        elif self.flare_state == "warning" and self._flare_timer <= 0.0:
            self.flare_state = "flare"
            self._flare_duration = self.rng.uniform(*FLARE_DURATION_DAYS_RANGE) * SIM_SECONDS_PER_DAY
            self.note("Solar flare in progress: radiation and particle storm.")
        elif self.flare_state == "flare":
            self._flare_duration -= dt
            if self._flare_duration <= 0.0:
                self.flare_state = "quiet"
                self._flare_timer = self.rng.uniform(*FLARE_QUIET_DAYS_RANGE) * SIM_SECONDS_PER_DAY
                self.note("Solar flare has passed. Conditions quiet.")

        self._debris_timer -= dt
        if self.debris_active:
            if self._debris_timer <= 0.0:
                self.debris_active = False
                self._debris_timer = DEBRIS_SEASON_PERIOD_DAYS * SIM_SECONDS_PER_DAY
                self.note("Debris season has ended.")
        elif self._debris_timer <= 0.0:
            self.debris_active = True
            self._debris_timer = DEBRIS_SEASON_DURATION_DAYS * SIM_SECONDS_PER_DAY
            self.note("Debris season: micrometeorite flux rising for ships in flight.")

        # Weather wear applies only to ships actually in flight; docked ships
        # sit inside the colony's shielding.
        wear = 0.0
        if self.flare_state == "flare":
            wear += FLARE_WEAR_PCT_PER_DAY
        if self.debris_active:
            wear += DEBRIS_WEAR_PCT_PER_DAY
        if wear <= 0.0:
            return
        for ship in self.ships:
            mission = self.missions.get(ship.name)
            if mission is None or mission.leg not in (Leg.OUTBOUND, Leg.INBOUND):
                continue
            current = self.hull.get(ship.name, HULL_MAX_PCT)
            floor = float(getattr(self, "hull_floor", HULL_MIN_PCT))
            resist = 0.0
            if mission is not None:
                resist = max(
                    self.body_weather_resist(mission.target),
                    self.body_weather_resist(getattr(ship, "origin", "") or ""),
                )
            self.hull[ship.name] = max(floor, current - wear * (1.0 - resist) * dt_days)

    # -- gravitational perturbations ------------------------------------------
    def tick_perturbations(self, dt_days: float) -> None:
        """Occasionally shift a belt body's orbit as a passer-by flies by.

        Only this sim's copy of the body table changes; window caches are
        dropped so every new plan is solved against the new geometry. Ships
        already in flight keep their conics -- the capture burn bills whatever
        the miss actually costs, which is exactly how a perturbation should
        bite.
        """
        if dt_days <= 0.0:
            return
        self._perturb_timer -= dt_days * SIM_SECONDS_PER_DAY
        if self._perturb_timer > 0.0:
            return
        self._perturb_timer = self.rng.uniform(
            PERTURB_MIN_INTERVAL_DAYS, PERTURB_MAX_INTERVAL_DAYS
        ) * SIM_SECONDS_PER_DAY

        candidates = [key for key in TRADE_TARGETS if key in self.bodies]
        if not candidates:
            return
        key = self.rng.choice(candidates)
        body = self.bodies[key]
        el = body.elements
        da = self.rng.uniform(*PERTURB_DA_FRACTION) * self.rng.choice((-1.0, 1.0))
        de = self.rng.uniform(-PERTURB_DE_MAX, PERTURB_DE_MAX)
        new_el = OrbitalElements(
            a=el.a * (1.0 + da),
            e=min(0.35, max(0.002, el.e + de)),
            i=el.i, raan=el.raan, argp=el.argp, nu=el.nu,
        )
        self.bodies[key] = replace(body, elements=new_el)
        self._window_cache.clear()
        self._round_trip_cache.clear()
        sign = "outward" if da > 0 else "inward"
        self.note(
            f"Gravitational perturbation: {body.name} drifts {sign} "
            f"({da * 100:+.1f}% semi-major axis). Re-plan transfers."
        )

    def weather_alert(self) -> str:
        """One-line status for the HUD; empty when all is quiet."""
        if self.flare_state == "warning":
            return "ALERT: solar flare warning - ships in flight"
        if self.flare_state == "flare":
            return "ALERT: solar flare in progress"
        if self.debris_active:
            return "Debris season: elevated hull wear in flight"
        return ""

    # -- multi-rev-aware window planning ---------------------------------------
    def _solve_window(self, origin_key: str, target_key: str, *,
                      epoch: float, min_departure_time: float | None = None,
                      max_departure_time: float | None = None):
        """Window search including multi-rev branches when they pay off."""
        from src.config import WINDOW_GRID_DEPART, WINDOW_GRID_TOF

        return window_solver.solve_window_multi(
            self.bodies[origin_key].elements, self.bodies[target_key].elements, MU_SUN,
            origin_key=origin_key, target_key=target_key,
            n_depart=WINDOW_GRID_DEPART, n_tof=WINDOW_GRID_TOF,
            epoch=epoch, min_departure_time=min_departure_time,
            max_departure_time=max_departure_time,
            max_revs=self._max_revs,
            multi_rev_min_saving=self._multi_rev_min_saving,
        )

    def launch_window(self, origin_key: str, target_key: str, refresh: bool = False):
        """Multi-rev-aware override of the cached window lookup."""
        cache_key = (origin_key, target_key)
        if not refresh and cache_key in self._window_cache:
            cached = self._window_cache[cache_key]
            if cached.departure_time >= self.time - 1e-9:
                return cached
        window = self._solve_window(origin_key, target_key, epoch=self.time,
                                    min_departure_time=self.time)
        if window is not None:
            self._window_cache[cache_key] = window
            self.stats["windows_solved"] += 1
        return window

    def plan_round_trip(self, origin_key: str, target_key: str, max_age: float | None = None):
        """Multi-rev-aware override of the round-trip planner.

        Semantics mirror the base implementation (cache with TTL, stale
        outbound re-solved from now, inbound bounded below by arrival) but
        every window search may consider multi-rev branches.
        """
        # Core semantics: ``max_age=None`` means "fresh pricing" (no cache
        # read) -- dispatch depends on that; a TTL is passed by callers that
        # merely want a recent estimate.
        cache_key = (origin_key, target_key)
        if max_age is not None:
            cached = self._round_trip_cache.get(cache_key)
            if cached is not None and (self.time - cached[0]) < max_age:
                return cached[1], cached[2]

        outbound = self.launch_window(origin_key, target_key)
        if outbound is None:
            return None, None
        if outbound.departure_time < self.time - 1e-9:
            outbound = self._solve_window(origin_key, target_key, epoch=self.time,
                                          min_departure_time=self.time)
            if outbound is None:
                return None, None
        arrival = outbound.departure_time + outbound.tof
        inbound = self._solve_window(target_key, origin_key, epoch=arrival,
                                     min_departure_time=arrival)
        if inbound is not None:
            self._round_trip_cache[cache_key] = (self.time, outbound, inbound)
        return outbound, inbound

    # -- stepping --------------------------------------------------------------
    def step(self, dt_days: float) -> list[LogEntry]:
        """Tick the ops layer (crew, weather) on top of the base event step.

        The base class processes mission events at their exact instants; the
        crew and weather ticks apply their per-day rates across the whole
        ``dt_days``, which is exact enough at the step sizes the game runs.
        """
        entries = super().step(dt_days)
        self.tick_weather(dt_days)
        self.tick_crew(dt_days)
        self.tick_perturbations(dt_days)
        self.tick_depots(dt_days)
        self._depot_refuel_waiting(dt_days)
        self._tanker_fill_depot(dt_days)
        self._depot_drones_load(dt_days)
        self._refinery_smelt_waiting(dt_days)
        self.tick_swarms(dt_days)
        self.tick_rival(dt_days)
        # Observatories grant RP via stats side-channel for the game layer.
        rp = self.tick_observatories(dt_days)
        if rp > 0.0:
            self.stats["observatory_rp"] = float(self.stats.get("observatory_rp", 0.0)) + rp
        return entries

    # -- mission hooks (wear, depletion, incidents) --------------------------
    def _pilot_refund(self, ship: Ship, spent_ms: float) -> None:
        """Hand back the pilot discount on a burn the core just billed."""
        if spent_ms <= 0.0:
            return
        ship.delta_v += spent_ms * self.pilots_discount(ship.name)

    def _depart(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._depart(ship, mission)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))
        self.last_active[ship.name] = self.time

    def _depot_topup_on_arrival(self, ship: Ship, mission: Mission) -> None:
        """Docking at a depot body: draw the ride home from its tank.

        The base class checks return-leg affordability at the capture instant,
        so the fuel the ship needs has to be in its tank *before* that check
        runs -- this is the gas-station stop, not a trickle.
        """
        depot = self.depots.get(mission.target)
        if depot is None or mission.return_window is None:
            return
        target = self.bodies[mission.target]
        _, v_target = window_solver.body_state(target.elements, MU_SUN, self.time)
        _, v_ship = ship.state_at(self.time)
        dv_match_ms = self.delta_v_km_s(float(np.linalg.norm(v_ship - v_target))) * 1000.0
        if dv_match_ms > ship.delta_v:
            return  # the capture itself will fail; nothing to service yet
        need = self.delta_v_km_s(mission.return_window.total_delta_v) * 1000.0
        shortfall = max(0.0, need - (ship.delta_v - dv_match_ms))
        headroom = self.class_spec(ship.name)["delta_v"] - ship.delta_v
        draw = min(headroom, depot.fuel_ms, shortfall + 2000.0)
        if draw > 0.0:
            ship.delta_v += draw
            depot.fuel_ms -= draw
            self.note(
                f"{ship.name} refuels at the {self.bodies[mission.target].name} depot "
                f"(+{draw:,.0f} m/s, {depot.fuel_ms:,.0f} m/s left)."
            )

    def _smelt_hold(self, ship: Ship, body_key: str, batches: int) -> int:
        """Run up to ``batches`` smelting passes over a hold; returns runs."""
        refinery = self.refineries.get(body_key)
        if refinery is None:
            return 0
        done = 0
        for _ in range(batches):
            recipe = self._first_craftable_recipe(ship)
            if recipe is None:
                break
            for ore, amount in recipe["input"].items():
                ship.cargo[ore] = ship.cargo.get(ore, 0.0) - amount
            ship.cargo[recipe["output"]] = ship.cargo.get(recipe["output"], 0.0) + recipe["amount"]
            refinery.batches_done += 1
            done += 1
        return done

    def _capture(self, ship: Ship, mission: Mission, target) -> None:
        if mission.leg is Leg.OUTBOUND:
            self._depot_topup_on_arrival(ship, mission)
            if self.refineries.get(mission.target) is not None:
                smelted = self._smelt_hold(ship, mission.target, REFINERY_ARRIVAL_BATCHES)
                if smelted:
                    self.note(
                        f"{ship.name}'s ore is smelted at the "
                        f"{self.bodies[mission.target].name} refinery "
                        f"({smelted} batches: {dict((k, round(v, 1)) for k, v in ship.cargo.items() if v > 0)})."
                    )
        inflight = self._inflight.pop(ship.name, None)
        before = ship.delta_v
        super()._capture(ship, mission, target)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))

        # Multi-stop transfer: after arriving at a hop body, chain the next leg
        # instead of flying the auto-return the core planned.
        if mission.leg is Leg.WAITING and self.routes.get(ship.name):
            # Only chain when this arrival was a hop (queue still has legs).
            if self._abort_return_and_continue(ship, mission):
                return

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

        # Success: draw the vein down, pay the crew's pride, charge drilling.
        self.ledger.commit(body_key, payload)
        self.stats["ore_mined_t"] += sum(payload.values())
        self.stats["captures_by_body"][body_key] = self.stats["captures_by_body"].get(body_key, 0) + 1
        if self.pending_deliveries:
            delivered_total = float(sum(self.pending_deliveries[-1].cargo.values()))
            if delivered_total >= ship.capacity * 0.98:
                self.stats["full_returns"] += 1
        self.last_active[ship.name] = self.time
        for member in self.crew.get(ship.name, []):
            member.morale = min(CREW_MORALE_MAX, member.morale + CREW_MORALE_CAPTURE_BONUS)
        if self.mining_mode == "drill":
            self.hull[ship.name] = max(
                HULL_MIN_PCT, self.hull[ship.name] - MINING_DRILL_WEAR_PCT
            )

        # Incident roll: drilling is riskier, a tired hull riskier still, and
        # an exhausted or sullen crew multiplies all of it.
        chance = self.incident_chance_drill if self.mining_mode == "drill" else self.incident_chance_scrape
        chance += INCIDENT_LOW_HULL_FACTOR * max(0.0, MINING_LOW_HULL_YIELD_PCT - self.hull[ship.name]) / 100.0
        chance *= self.crew_incident_factor(ship.name)
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


    def _abort_return_and_continue(self, ship: Ship, mission: Mission) -> bool:
        """If a multi-stop queue remains, cancel the auto-return and hop onward."""
        queue = self.routes.get(ship.name) or []
        if not queue:
            return False
        # Ship is WAITING at mission.target with a return_window home -- drop it.
        if ship.name in self.missions:
            # Treat capture as a successful hop endpoint; clear mission so we can re-dispatch.
            # Mass already counted by core if cargo was delivered; transfer hops had empty cargo.
            self.missions.pop(ship.name, None)
        ship.origin = mission.target
        self._continue_route(ship)
        return True

    def _complete_run(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._complete_run(ship, mission)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))
        self.last_active[ship.name] = self.time
        # Multi-stop: if more legs remain, depart the next hop immediately.
        if self.routes.get(ship.name):
            self._continue_route(ship)

    # -- reporting -----------------------------------------------------------
    def ship_report(self, ship: Ship) -> dict:
        report = super().ship_report(ship)
        report["class"] = self.ship_class.get(ship.name, DEFAULT_SHIP_CLASS)
        report["hull"] = self.hull.get(ship.name, HULL_MAX_PCT)
        report["capacity"] = ship.capacity
        report["dv_max"] = self.effective_delta_v(ship.name)
        report["parts"] = dict(self.upgrades.get(ship.name, {}))
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
                "upgrades": dict(self.upgrades.get(ship.name, {})),
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
                "revs": int(getattr(window, "revs", 0)),
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
            "crew": {name: [member.to_json() for member in roster]
                     for name, roster in self.crew.items()},
            "depots": [depot.to_json() for depot in self.depots.values()],
            "tech_mults": dict(self.tech_mults),
            "routes": {name: [leg.__dict__ if hasattr(leg, "__dict__") else leg for leg in legs]
                       for name, legs in self.routes.items()},
            "standing_orders": dict(self.standing_orders),
            "swarms": {k: dict(v) for k, v in self.swarms.items()},
            "swarm_cooldown": dict(self.swarm_cooldown),
            "survey_bonus": {k: dict(v) for k, v in self.survey_bonus.items()},
            "isru_spikes": dict(self.isru_spikes),
            "station_modules": {k: dict(v) for k, v in self.station_modules.items()},
            "rival_enabled": bool(self.rival_enabled),
            "rival_dump_timer": float(getattr(self, "_rival_dump_timer", RIVAL_DUMP_PERIOD_DAYS)),
            "hull_floor": float(getattr(self, "hull_floor", HULL_MIN_PCT)),
            "refineries": [r.to_json() for r in self.refineries.values()],
            "botanists": self.botanists,
            "perturb_timer": self._perturb_timer,
            "body_overrides": {
                key: {"a": body.elements.a, "e": body.elements.e}
                for key, body in self.bodies.items()
                if body is not BODIES.get(key)
            },
            "last_active": dict(self.last_active),
            "weather": {
                "flare_state": self.flare_state,
                "flare_timer": self._flare_timer,
                "flare_duration": self._flare_duration,
                "debris_timer": self._debris_timer,
                "debris_active": self.debris_active,
            },
            "rng": rng_to_json(self.rng),
            "version": 2,
        }

    @classmethod
    def from_json(cls, data: dict) -> "OpsSimulation":
        sim = cls.__new__(cls)
        sim.time = float(data["time"])
        sim.warp_days_per_second = float(data["warp_days_per_second"])
        sim.bodies = dict(BODIES)
        for key, override in data.get("body_overrides", {}).items():
            body = sim.bodies.get(key)
            if body is not None:
                el = body.elements
                sim.bodies[key] = replace(body, elements=OrbitalElements(
                    a=float(override["a"]), e=float(override["e"]),
                    i=el.i, raan=el.raan, argp=el.argp, nu=el.nu))
        sim.ships = []
        sim.missions = {}
        sim.log = []
        sim._window_cache = {}
        sim._round_trip_cache = {}
        sim._next_scan_time = float(data["next_scan_time"])
        sim.stats = dict(data["stats"])
        sim.stats.setdefault("full_returns", 0)
        sim.stats.setdefault("captures_by_body", {})
        sim.pending_deliveries = []
        sim.ship_class = {}
        sim.hull = {}
        # Per-instance knobs normally assigned in __init__; __new__ skips it.
        sim.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        sim.incident_chance_drill = INCIDENT_CHANCE_DRILL
        sim.hull_critical_pct = HULL_CRITICAL_PCT
        sim._max_revs = PLANNING_MAX_REVS
        sim._multi_rev_min_saving = PLANNING_MULTI_REV_MIN_SAVING
        sim.crew = {}
        sim.upgrades = {}
        sim.tech_mults = {}
        sim.routes = {}
        sim.standing_orders = {"prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}
        sim.swarms = {}
        sim.swarm_cooldown = {}
        sim.survey_bonus = {}
        sim.isru_spikes = {}
        sim.station_modules = {}
        sim.rival_enabled = False
        sim._rival_dump_timer = float(RIVAL_DUMP_PERIOD_DAYS)
        sim.last_active = {}
        sim.trade_targets = tuple(TRADE_TARGETS)
        sim.bodies = dict(sim.bodies)
        sim._install_comet()
        sim.depots = {d["body_key"]: Depot.from_json(d) for d in data.get("depots", [])}
        sim.tech_mults = {k: float(v) for k, v in data.get("tech_mults", {}).items()}
        sim.hull_floor = float(data.get("hull_floor", HULL_MIN_PCT))
        from src.routes import RouteLeg
        sim.routes = {}
        for name, legs in data.get("routes", {}).items():
            sim.routes[name] = [RouteLeg(**leg) if isinstance(leg, dict) else leg for leg in legs]
        sim.standing_orders = dict(data.get("standing_orders", {
            "prefer_hops": True, "destinations": [], "min_depot_fuel": 4000.0}))
        sim.swarms = {k: dict(v) for k, v in data.get("swarms", {}).items()}
        sim.swarm_cooldown = {k: float(v) for k, v in data.get("swarm_cooldown", {}).items()}
        sim.survey_bonus = {k: dict(v) for k, v in data.get("survey_bonus", {}).items()}
        sim.isru_spikes = {k: int(v) for k, v in data.get("isru_spikes", {}).items()}
        sim.station_modules = {k: {mk: int(mv) for mk, mv in v.items()}
                               for k, v in data.get("station_modules", {}).items()}
        sim.rival_enabled = bool(data.get("rival_enabled", False))
        sim._rival_dump_timer = float(data.get("rival_dump_timer", RIVAL_DUMP_PERIOD_DAYS))
        sim.refineries = {r["body_key"]: Refinery.from_json(r) for r in data.get("refineries", [])}
        sim.botanists = int(data.get("botanists", 0))
        sim._perturb_timer = float(data.get("perturb_timer",
                                            PERTURB_MIN_INTERVAL_DAYS * SIM_SECONDS_PER_DAY))
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
            sim.upgrades[ship.name] = {k: int(v) for k, v in ship_data.get("upgrades", {}).items()}

        # Crew rosters; falls back to fresh hires for saves from older
        # versions that predate the crew system.
        for name, roster in data.get("crew", {}).items():
            sim.crew[name] = [CrewMember.from_json(member) for member in roster]
        for ship in sim.ships:
            if ship.name not in sim.crew:
                sim._hire_crew(ship.name)
        sim.last_active = {name: float(t) for name, t in data.get("last_active", {}).items()}

        weather = data.get("weather", {})
        sim.flare_state = weather.get("flare_state", "quiet")
        sim._flare_timer = float(weather.get("flare_timer", FLARE_QUIET_DAYS_RANGE[0] * SIM_SECONDS_PER_DAY))
        sim._flare_duration = float(weather.get("flare_duration", 0.0))
        sim._debris_timer = float(weather.get("debris_timer", DEBRIS_SEASON_PERIOD_DAYS * SIM_SECONDS_PER_DAY))
        sim.debris_active = bool(weather.get("debris_active", False))

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
                revs=int(w.get("revs", 0)),
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
