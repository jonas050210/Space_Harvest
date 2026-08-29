"""Swarm and survey mixin - extracted from simulation.py."""

from __future__ import annotations

from src.config import (
    SIM_SECONDS_PER_DAY,
    SURFACE_ISRU_DEPOT_GEN_BONUS,
    SURFACE_ISRU_MAX_PER_BODY,
    SURFACE_SURVEY_BONUS,
    SURFACE_SURVEY_DAYS,
    SWARM_BASE_DRONES,
    SWARM_COOLDOWN_DAYS,
    SWARM_DRONES_PER_BAY,
    SWARM_DURATION_DAYS,
    SWARM_MAX_DRONES,
    SWARM_YIELD_T_PER_DRONE_DAY,
)
from src.simulation.orbital_sim import Delivery


class SwarmMixin:

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

