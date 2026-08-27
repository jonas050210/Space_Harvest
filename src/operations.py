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
from dataclasses import dataclass, replace

import numpy as np

from .config import (
    CREW_BOTANIST_SAVING_CAP,
    CREW_BOTANIST_WATER_SAVING,
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
    PERTURB_DA_FRACTION,
    PERTURB_DE_MAX,
    PERTURB_MAX_INTERVAL_DAYS,
    PERTURB_MIN_INTERVAL_DAYS,
    SHIP_CLASSES,
    SIM_SECONDS_PER_DAY,
)
from .market import rng_from_json, rng_to_json
from .maths.elements import OrbitalElements
from .maths import windows as window_solver
from .mining import YieldLedger, plan_extraction
from .simulation.bodies import BODIES
from .simulation.bodies import BODIES, TRADE_TARGETS
from .simulation.orbital_sim import Delivery, Leg, LogEntry, Mission, OrbitalSimulation, Ship


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
        #: colony-side botanists (they work the hydroponics racks, not ships)
        self.botanists = 0
        # Gravitational perturbation clock: this sim owns its own body table,
        # so a passing body nudges *this* campaign's orbits and nothing else.
        self._perturb_timer = self.rng.uniform(
            PERTURB_MIN_INTERVAL_DAYS, PERTURB_MAX_INTERVAL_DAYS
        ) * SIM_SECONDS_PER_DAY
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
                capacity_t=ship.capacity,
                mode=self.mining_mode,
                mine_bonus=spec["mine_bonus"] * self.crew_yield_factor(ship.name),
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
                for member in roster:
                    member.fatigue = max(0.0, member.fatigue - CREW_FATIGUE_RECOVERY_PER_DAY * dt_days)
                    if bored and member.fatigue < 30.0:
                        member.morale = max(
                            CREW_MORALE_BOREDOM_FLOOR,
                            member.morale - CREW_MORALE_BOREDOM_DRAIN_PER_DAY * dt_days,
                        )
                    else:
                        member.morale = min(CREW_MORALE_MAX, member.morale + CREW_MORALE_REST_PER_DAY * dt_days)
            else:
                if mission.leg is Leg.WAITING:
                    rate = CREW_FATIGUE_PER_DAY_LAYOVER
                elif mission.leg is Leg.PENDING:
                    rate = CREW_FATIGUE_PER_DAY_PENDING
                else:
                    rate = CREW_FATIGUE_PER_DAY_FLYING
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
        """Fraction of every burn refunded by skilled piloting (ops-layer)."""
        count = sum(1 for member in self.crew.get(ship_name, []) if member.role == "pilot")
        return min(CREW_PILOT_DISCOUNT_CAP, count * CREW_PILOT_BURN_DISCOUNT)

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
            self.hull[ship.name] = max(HULL_MIN_PCT, current - wear * dt_days)

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

    def _capture(self, ship: Ship, mission: Mission, target) -> None:
        inflight = self._inflight.pop(ship.name, None)
        before = ship.delta_v
        super()._capture(ship, mission, target)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))

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

    def _complete_run(self, ship: Ship, mission: Mission) -> None:
        before = ship.delta_v
        super()._complete_run(ship, mission)
        spent = before - ship.delta_v
        self._pilot_refund(ship, spent)
        self._apply_wear(ship, spent * (1.0 - self.pilots_discount(ship.name)))
        self.last_active[ship.name] = self.time

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
            "crew": {name: [member.to_json() for member in roster]
                     for name, roster in self.crew.items()},
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
        sim.pending_deliveries = []
        sim.ship_class = {}
        sim.hull = {}
        # Per-instance knobs normally assigned in __init__; __new__ skips it.
        sim.incident_chance_scrape = INCIDENT_CHANCE_SCRAPE
        sim.incident_chance_drill = INCIDENT_CHANCE_DRILL
        sim.hull_critical_pct = HULL_CRITICAL_PCT
        sim.crew = {}
        sim.last_active = {}
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
