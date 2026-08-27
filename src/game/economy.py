# Construction costs and prices.
from . import config, state

def drone_cost(drone_state):
    # Simple scaling: the first four drones are cheaper.
    base = {"iron": 60, "ice": 30}
    factor = 1.0 + max(0, drone_state.get("id", 1) - 2) * 0.15
    result = {}
    for k, v in base.items():
        result[k] = int(v * factor)
    return result

def module_available(mod_name, current_modules):
    # Limit each module to two copies.
    return current_modules.count(mod_name) < 2

def upgrade_available(upgrade_key, drone_state):
    info = config.DRONE_UPGRADES.get(upgrade_key, {})
    max_lvl = info.get("levels", 0)
    current = drone_state.get(f"level_{upgrade_key}", 0)
    return current < max_lvl

def upgrade_cost(upgrade_key, current_level):
    info = config.DRONE_UPGRADES.get(upgrade_key, {})
    base = info.get("cost", {})
    factor = 1.0 + current_level * 0.5
    result = {}
    for k, v in base.items():
        result[k] = int(v * factor)
    return result
