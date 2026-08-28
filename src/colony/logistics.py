"""Storage and colony logistics accounting."""

from . import research

BASE_STORAGE_CAPACITY = 300
STORAGE_MODULE_CAPACITY = 250


def capacity_for(state, resource_key):
    """Return the current capacity for a storable resource."""
    capacity = BASE_STORAGE_CAPACITY + state.get("modules", []).count("storage") * STORAGE_MODULE_CAPACITY
    if research.unlocked(state, "logistics_protocols"):
        capacity += 150
    capacity += float(state.get("warehouse_bonus_t", 0.0) or 0.0)
    return capacity


def available_capacity(state, resource_key):
    return max(0, capacity_for(state, resource_key) - state.get("resources", {}).get(resource_key, 0))


def store(state, resources):
    """Store a delivery and return dictionaries for stored and overflow resources."""
    stored, overflow = {}, {}
    state.setdefault("resources", {})
    for resource_key, amount in resources.items():
        amount = max(0, amount)
        accepted = min(amount, available_capacity(state, resource_key))
        state["resources"][resource_key] = state["resources"].get(resource_key, 0) + accepted
        stored[resource_key] = accepted
        overflow[resource_key] = amount - accepted
    stats = state.setdefault("logistics", {}).setdefault("lifetime_delivered", {})
    delivered_total = 0
    for resource_key, amount in stored.items():
        stats[resource_key] = stats.get(resource_key, 0) + amount
        delivered_total += amount
    state.setdefault("run_stats", {}).setdefault("resources_delivered", 0)
    state["run_stats"]["resources_delivered"] += delivered_total
    return stored, overflow


def summary(state):
    """Return UI-friendly logistics metrics."""
    resources = state.get("resources", {})
    from src.config import MINING_ORES
    used = sum(resources.get(key, 0) for key in MINING_ORES)
    capacity = capacity_for(state, "shared") * 5
    return {"used": used, "capacity": capacity, "delivered": sum(state.get("logistics", {}).get("lifetime_delivered", {}).values())}
