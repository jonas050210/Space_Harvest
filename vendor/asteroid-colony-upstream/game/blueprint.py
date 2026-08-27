# Blueprint system.
# Saves and loads complete station layouts (modules, machines, drones, and asteroids).
import json, os, time
from . import config, state as st_mod

BLUEPRINT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blueprints")

def ensure_dir():
    if not os.path.isdir(BLUEPRINT_DIR):
        os.makedirs(BLUEPRINT_DIR)

def list_blueprints():
    ensure_dir()
    files = [f for f in os.listdir(BLUEPRINT_DIR) if f.endswith(".json")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(BLUEPRINT_DIR, x)), reverse=True)
    return files

def save_blueprint(name, game_state, asteroid_positions, drone_states, module_list, machine_counts):
    ensure_dir()
    path = os.path.join(BLUEPRINT_DIR, f"{name}.json")
    data = {
        "timestamp": time.time(),
        "name": name,
        "state": {
            "resources": game_state.get("resources", {}),
            "population": game_state.get("population", 0),
            "drones": game_state.get("drones", []),
            "modules": game_state.get("modules", []),
            "machines": game_state.get("machines", {}),
            "research_points": game_state.get("research_points", 0),
            "research": game_state.get("research", {}),
            "logistics": game_state.get("logistics", {}),
            "station_layout": game_state.get("station_layout", {}),
            "contracts": game_state.get("contracts", {}),
            "current_region": game_state.get("current_region", "inner_belt"),
            "discovered_regions": game_state.get("discovered_regions", ["inner_belt"]),
            "derelict_scanned": game_state.get("derelict_scanned", False),
            "milestones": game_state.get("milestones", []),
            "claimed_milestones": game_state.get("claimed_milestones", []),
            "run_stats": game_state.get("run_stats", {}),
        },
        "asteroids": [
            {"pos": [a.x, a.y, a.z], "amount": getattr(a, 'amount', 0), "type": getattr(a, 'res_type', 'ice')}
            for a in asteroid_positions
        ],
        "layout_version": "0.9.2",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

def load_blueprint(name, app_ref):
    ensure_dir()
    path = os.path.join(BLUEPRINT_DIR, f"{name}.json")
    if not os.path.isfile(path):
        print(f"[Blueprint] File not found: {name}")
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Load resources, population, drones, modules, and machines.
    app_ref.state["resources"] = data.get("state", {}).get("resources", app_ref.state.get("resources", {}))
    app_ref.state["population"] = data.get("state", {}).get("population", app_ref.state.get("population", 0))
    app_ref.state["drones"] = data.get("state", {}).get("drones", app_ref.state.get("drones", []))
    app_ref.state["modules"] = data.get("state", {}).get("modules", app_ref.state.get("modules", []))
    app_ref.state["machines"] = data.get("state", {}).get("machines", app_ref.state.get("machines", {}))
    for key in ("research_points", "research", "logistics", "station_layout", "contracts", "current_region", "discovered_regions", "derelict_scanned", "milestones", "claimed_milestones", "run_stats"):
        app_ref.state[key] = data.get("state", {}).get(key, app_ref.state.get(key))
    # Asteroid reconstruction is intentionally deferred in this lightweight implementation.
    print(f"[Blueprint] Loaded: {name} (version {data.get('layout_version', '?')})")
    return True
