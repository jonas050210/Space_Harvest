# Game state.
import time, random
from . import config, savegame, settings, research, station_builder

def initial_state():
    return {
        "resources": {
            "ice": 200, "iron": 150, "gold": 10, "silver": 5, "platinum": 0, "energy": 20, "water": 0, "components": 0, "electronics": 0,
        },
        "population": 3,
        "max_pop": 8,
        "max_energy": 30,
        "drones": [
            {"id": 1, "level_speed": 0, "level_cargo": 0, "level_mining": 0, "state": "idle", "target": None, "cargo": 0, "health": 1.0, "role": "miner"},
            {"id": 2, "level_speed": 0, "level_cargo": 0, "level_mining": 0, "state": "idle", "target": None, "cargo": 0, "health": 1.0, "role": "miner"},
        ],
        "modules": ["drone_bay", "solar_panel"],
        "station_level": 1,
        "difficulty": settings.load().get("difficulty", config.DEFAULT_DIFFICULTY),
        "language": settings.load().get("language", "en"),
        "score": 0,
        "time_played": 0.0,
        "tick": 0,
        "events_active": [],
        "highscore": 0,
        "research_points": 0.0,
        "research": {"unlocked": []},
        "logistics": {"lifetime_delivered": {}, "production": {}},
        "station_layout": {"occupied": [], "placements": []},
        "contracts": {"active": [], "completed": [], "reputation": {}},
        "current_region": "inner_belt",
        "discovered_regions": ["inner_belt"],
        "derelict_scanned": False,
        "milestones": [],
        "claimed_milestones": [],
        "run_stats": {"resources_delivered": 0, "contracts_completed": 0, "regions_visited": 1, "artifacts_recovered": 0},
        "machines": {},  # Keys are machine identifiers; values are purchased counts.
    }

def get_diff_factor(state):
    name = state.get("difficulty", config.DEFAULT_DIFFICULTY)
    return config.DIFFICULTY.get(name, 1.0)

def resource_ok(state, cost_dict, factor=1.0):
    mult = get_diff_factor(state) * factor
    for k, v in cost_dict.items():
        need = v * mult
        if state["resources"].get(k, 0) < need:
            return False
    return True

def deduct_resources(state, cost_dict, factor=1.0):
    mult = get_diff_factor(state) * factor
    for k, v in cost_dict.items():
        state["resources"][k] -= v * mult

def add_resources(state, res_dict):
    for k, v in res_dict.items():
        state["resources"][k] = state["resources"].get(k, 0) + v

def energy_delta(modules):
    delta = 0
    for m in modules:
        info = config.MODULES.get(m, {})
        delta += info.get("energy_use", 0)
    return delta

def get_machine_cost(machine_key, state):
    info = config.MACHINES.get(machine_key)
    if not info:
        return {}
    count = state.get("machines", {}).get(machine_key, 0)
    mult = info.get("multiplier", 1.0) ** count
    result = {}
    for k, v in info.get("base_cost", {}).items():
        result[k] = int(v * mult)
    return result

def add_machine_output(state):
    # Each machine produces resources per tick.
    delta = {}
    for key, info in config.MACHINES.items():
        count = state.get("machines", {}).get(key, 0)
        if count > 0:
            output_multiplier = (1.25 if key == "refinery" and research.unlocked(state, "automated_refining") else 1.0) * (1 + station_builder.placement_bonus(state)) * config.REGION_ECONOMY.get(state.get("current_region", "inner_belt"), {}).get("machine_output", 1.0)
            for k, v in info.get("output_per_tick", {}).items():
                delta[k] = delta.get(k, 0) + v * count * output_multiplier
    # Energy consumption.
    energy_delta = 0
    for key, info in config.MACHINES.items():
        count = state.get("machines", {}).get(key, 0)
        if count > 0:
            energy_delta += info.get("energy_use", 0) * count
    for k, v in delta.items():
        state.setdefault("resources", {})[k] = state.get("resources", {}).get(k, 0) + v
    state.setdefault("resources", {})["energy"] = state.get("resources", {}).get("energy", 0) - energy_delta

def energy_tick(state):
    delta = energy_delta(state["modules"])
    # Solar-panel baseline energy is already included in the delta.
    # Hard difficulty applies a global -1 penalty.
    delta += -1 if get_diff_factor(state) > 1.2 else 0
    # Life support consumes 0.5 energy per five population.
    delta -= int(state.get("population", 0) / 5) * 0.5
    state["resources"]["energy"] += delta
    # Keep energy within valid bounds.
    max_e = state.get("max_energy", 30)
    # Modules do not currently increase maximum energy.
    # The refinery provides a bonus rather than an energy-cap increase.
    # Life support increases population capacity, not energy capacity.
    if state["resources"]["energy"] > max_e:
        state["resources"]["energy"] = max_e
    if state["resources"]["energy"] < 0:
        state["resources"]["energy"] = 0
