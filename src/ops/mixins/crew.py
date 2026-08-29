"""Crew mixin extracted from simulation.py - no behavior change."""

from __future__ import annotations

from src.config import (
    CREW_BOTANIST_SAVING_CAP,
    CREW_BOTANIST_WATER_SAVING,
    CREW_FIRE_MORALE_HIT,
    CREW_MAX_ROSTER,
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
    CREW_PILOT_BURN_DISCOUNT,
    CREW_PILOT_DISCOUNT_CAP,
    CREW_FATIGUE_PER_DAY_FLYING,
    CREW_FATIGUE_PER_DAY_LAYOVER,
    CREW_FATIGUE_PER_DAY_PENDING,
    CREW_FATIGUE_RECOVERY_PER_DAY,
    CREW_IDLE_BOREDOM_DAYS,
    FLARE_MORALE_DRAIN_PER_DAY,
    SIM_SECONDS_PER_DAY,
)
from src.config.parts import PARTS_CATALOG
from src.ops.structures import CrewMember
from src.simulation.orbital_sim import Leg


CREW_ROSTER_TEMPLATE = {"pilot": 1, "miner": 2, "engineer": 1}
_AWAY_LEGS = {Leg.OUTBOUND, Leg.INBOUND, Leg.WAITING, Leg.PENDING}


class CrewMixin:

    def _hire_crew(self, ship_name: str) -> None:
            """Give a ship its roster: deterministic draws from the name pools."""
            roster: list[CrewMember] = []
            for role, seats in CREW_ROSTER_TEMPLATE.items():
                for _ in range(seats):
                    name = f"{self.rng.choice(CREW_NAMES_FIRST)} {self.rng.choice(CREW_NAMES_LAST)}"
                    roster.append(CrewMember(name=name, role=role))
            self.crew[ship_name] = roster

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
                self.note("A botanist joins the colony hydroponics roster.")
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
