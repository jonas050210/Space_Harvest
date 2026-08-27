# Space Station Designer.
# Station design and automation focused on the economy rather than combat.
from .. import config, state as st_mod

def get_station_efficiency(state):
    modules = state.get("modules", [])
    machines = state.get("machines", {})
    total_output = 0
    for key, info in config.MACHINES.items():
        total_output += info.get("output_per_tick", {}).get("iron", 0) * machines.get(key, 0)
    return min(100, total_output * 5 + len(modules) * 10)

def design_bonus(state):
    # Bonus based on the number of modules and machines.
    bonus = len(state.get("modules", [])) * 2 + sum(state.get("machines", {}).values()) * 3
    return bonus
