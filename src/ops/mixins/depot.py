"""Depot, refinery, station mixin - extracted from simulation.py."""

from __future__ import annotations

from src.config import (
    DEPOT_BUILD_COST,
    DEPOT_GENERATION_PER_LEVEL,
    REFINERY_BATCHES_PER_DAY,
    REFINERY_BUILD_COST,
    STATION_MODULE_CATALOG,
    SURFACE_ISRU_DEPOT_GEN_BONUS,
)
from src.config.parts import PARTS_CATALOG
from src.ops.structures import Depot, Refinery
from src.mining import plan_extraction
from src.simulation.bodies import TRADE_TARGETS
from src.simulation.orbital_sim import Leg


class DepotMixin:

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
