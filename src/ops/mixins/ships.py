"""Ships mixin - ship classes, parts, wear, buying."""

from __future__ import annotations

from src.config import (
    DEFAULT_SHIP_CLASS,
    FLEET_NAME_POOL,
    HULL_MAX_PCT,
    HULL_MIN_PCT,
    HULL_WEAR_PCT_PER_MS,
    SHIP_CLASSES,
    STATION_MODULE_CATALOG,
)
from src.config.parts import PARTS_CATALOG
from src.config import REFINERY_RECIPES
from src.simulation.orbital_sim import Ship


class ShipsMixin:

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


    @staticmethod
    def _first_craftable_recipe(ship: Ship):
        for recipe in REFINERY_RECIPES:
            if all(ship.cargo.get(ore, 0.0) >= amount for ore, amount in recipe["input"].items()):
                return recipe
        return None

