"""Weather and perturbations mixin - extracted from simulation.py."""

from __future__ import annotations

from dataclasses import replace

from src.config import (
    DEBRIS_SEASON_DURATION_DAYS,
    DEBRIS_SEASON_PERIOD_DAYS,
    DEBRIS_WEAR_PCT_PER_DAY,
    FLARE_DURATION_DAYS_RANGE,
    FLARE_EXPOSURE_BY_BODY,
    FLARE_QUIET_DAYS_RANGE,
    FLARE_WARNING_DAYS,
    FLARE_WEAR_PCT_PER_DAY,
    HULL_MAX_PCT,
    HULL_MIN_PCT,
    PERTURB_DA_FRACTION,
    PERTURB_DE_MAX,
    PERTURB_MAX_INTERVAL_DAYS,
    PERTURB_MIN_INTERVAL_DAYS,
    RIVAL_DUMP_PERIOD_DAYS,
    RIVAL_MINE_T_PER_DAY,
    SIM_SECONDS_PER_DAY,
)
from src.maths.elements import OrbitalElements
from src.simulation.bodies import TRADE_TARGETS
from src.simulation.orbital_sim import Leg


class WeatherMixin:

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
            flare_wear = FLARE_WEAR_PCT_PER_DAY if self.flare_state == "flare" else 0.0
            debris_wear = DEBRIS_WEAR_PCT_PER_DAY if self.debris_active else 0.0
            if flare_wear <= 0.0 and debris_wear <= 0.0:
                return
            for ship in self.ships:
                mission = self.missions.get(ship.name)
                if mission is None or mission.leg not in (Leg.OUTBOUND, Leg.INBOUND):
                    continue
                current = self.hull.get(ship.name, HULL_MAX_PCT)
                floor = float(getattr(self, "hull_floor", HULL_MIN_PCT))
                resist = 0.0
                exposure = 1.0
                if mission is not None:
                    resist = max(
                        self.body_weather_resist(mission.target),
                        self.body_weather_resist(getattr(ship, "origin", "") or ""),
                    )
                    # Solar exposure: bodies that skim the sun ride flares harder.
                    exposure = max(
                        FLARE_EXPOSURE_BY_BODY.get(mission.target, 1.0),
                        FLARE_EXPOSURE_BY_BODY.get(getattr(ship, "origin", "") or "", 1.0),
                    )
                wear = flare_wear * exposure + debris_wear
                self.hull[ship.name] = max(floor, current - wear * (1.0 - resist) * dt_days)

    def weather_alert(self) -> str:
            """One-line status for the HUD; empty when all is quiet."""
            if self.flare_state == "warning":
                return "ALERT: solar flare warning - ships in flight"
            if self.flare_state == "flare":
                return "ALERT: solar flare in progress"
            if self.debris_active:
                return "Debris season: elevated hull wear in flight"
            return ""

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
