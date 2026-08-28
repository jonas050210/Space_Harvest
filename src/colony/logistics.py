"""Storage, drone delivery, and colony logistics accounting."""

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


def deliver_drone_cargo(state, drone_state):
    """Unload a drone's typed cargo into storage and clear its hold."""
    resource_key = drone_state.get("cargo_resource")
    amount = drone_state.get("cargo", 0)
    if not resource_key or amount <= 0:
        return {}, {}
    stored, overflow = store(state, {resource_key: amount})
    drone_state["cargo"] = 0
    drone_state["cargo_resource"] = None
    return stored, overflow


def summary(state):
    """Return UI-friendly logistics metrics."""
    resources = state.get("resources", {})
    from src.config import MINING_ORES
    used = sum(resources.get(key, 0) for key in MINING_ORES)
    capacity = capacity_for(state, "shared") * 5
    return {"used": used, "capacity": capacity, "delivered": sum(state.get("logistics", {}).get("lifetime_delivered", {}).values())}


def process_production(state):
    """Run one production cycle for every recipe supported by installed modules."""
    from . import config

    results = {}
    modules = state.get("modules", [])
    unlocked = state.get("research", {}).get("unlocked", [])
    for key, recipe in config.PRODUCTION_RECIPES.items():
        if recipe["module"] not in modules or recipe.get("research") and recipe["research"] not in unlocked:
            continue
        if all(state.get("resources", {}).get(resource, 0) >= amount for resource, amount in recipe["input"].items()):
            for resource, amount in recipe["input"].items():
                state["resources"][resource] -= amount
            stored, overflow = store(state, recipe["output"])
            results[key] = {"stored": stored, "overflow": overflow}
            state.setdefault("logistics", {}).setdefault("production", {})[key] = state["logistics"].get("production", {}).get(key, 0) + 1
    return results
