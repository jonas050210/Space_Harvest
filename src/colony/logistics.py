"""Storage and colony logistics accounting.

Simple shared-capacity model: every ore shares the same storage pool size,
modified by storage modules, research and warehouse bonuses. Overflow is
reported but not stored - the game layer decides what to do with it.
"""

from __future__ import annotations

from . import research

BASE_STORAGE_CAPACITY = 300
STORAGE_MODULE_CAPACITY = 250


def capacity_for(state: dict, resource_key: str) -> float:
    """Return current capacity for a storable resource (shared pool)."""
    capacity = BASE_STORAGE_CAPACITY + state.get("modules", []).count("storage") * STORAGE_MODULE_CAPACITY
    if research.unlocked(state, "logistics_protocols"):
        capacity += 150
    capacity += float(state.get("warehouse_bonus_t", 0.0) or 0.0)
    return float(capacity)


def available_capacity(state: dict, resource_key: str) -> float:
    return max(0.0, capacity_for(state, resource_key) - state.get("resources", {}).get(resource_key, 0))


def store(state: dict, resources: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Store a delivery and return (stored, overflow) dicts."""
    stored: dict[str, float] = {}
    overflow: dict[str, float] = {}
    state.setdefault("resources", {})
    for resource_key, amount in resources.items():
        amount = max(0.0, float(amount))
        accepted = min(amount, available_capacity(state, resource_key))
        state["resources"][resource_key] = state["resources"].get(resource_key, 0) + accepted
        stored[resource_key] = accepted
        overflow[resource_key] = amount - accepted
    stats = state.setdefault("logistics", {}).setdefault("lifetime_delivered", {})
    delivered_total = 0.0
    for resource_key, amount in stored.items():
        stats[resource_key] = stats.get(resource_key, 0) + amount
        delivered_total += amount
    state.setdefault("run_stats", {}).setdefault("resources_delivered", 0)
    state["run_stats"]["resources_delivered"] += delivered_total
    return stored, overflow


def summary(state: dict) -> dict[str, float]:
    """Return UI-friendly logistics metrics."""
    resources = state.get("resources", {})
    try:
        from src.config import MINING_ORES
        ores = MINING_ORES
    except Exception:
        ores = tuple(resources.keys())
    used = sum(float(resources.get(key, 0)) for key in ores)
    # Shared pool * 5 is legacy HUD heuristic - keep for compatibility
    capacity = capacity_for(state, "shared") * 5.0
    return {
        "used": used,
        "capacity": capacity,
        "delivered": float(sum(state.get("logistics", {}).get("lifetime_delivered", {}).values())),
    }
