"""Shared dataclasses for ops layer - extracted from simulation.py to reduce God Object size."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import (
    CREW_MORALE_START,
    DEPOT_CAPACITY_PER_LEVEL,
    DEPOT_GENERATION_PER_LEVEL,
    DEPOT_START_FUEL,
    DEPOT_UPGRADE_COST,
    DEPOT_UPGRADE_COST_GROWTH,
)


@dataclass
class Depot:
    """A player-built refuel station at a trade body."""

    body_key: str
    level: int = 1
    fuel_ms: float = DEPOT_START_FUEL
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
    """A player-built smelting station at a trade body."""

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
