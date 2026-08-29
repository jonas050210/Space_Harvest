"""Colony bridge - extracted from main.py God Object.

Owns the colony state and translates freighter deliveries into
upstream storage rules. Pure economy, no rendering.
"""

from __future__ import annotations

from src.colony import logistics as colony_logistics
from src.colony import state as colony_state
from src.config import LIFE_START_FOOD, LIFE_START_OXYGEN, LIFE_START_WATER


class Colony:
    """Bridges the orbital simulation into the existing colony economy."""

    def __init__(self):
        self.state = colony_state.initial_state()
        self.state["resources"]["oxygen"] = LIFE_START_OXYGEN
        self.state["resources"]["food"] = LIFE_START_FOOD
        self.state["resources"]["water"] = LIFE_START_WATER

    def receive(self, cargo: dict[str, float]) -> dict:
        """Store a freighter's delivery using the upstream storage rules."""
        payload = {key: float(amount) for key, amount in cargo.items() if amount > 0}
        if not payload:
            return {"stored": {}, "overflow": {}}
        stored, overflow = colony_logistics.store(self.state, payload)
        self.state["research_points"] = float(self.state.get("research_points", 0.0)) + 0.25 * sum(stored.values())
        return {"stored": stored, "overflow": overflow}

    def summary(self) -> dict:
        return colony_logistics.summary(self.state)
