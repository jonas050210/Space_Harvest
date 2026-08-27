"""Region travel, deep-space discovery, and trade-route progression."""

from . import config, contracts, research


def available_regions(state):
    unlocked = state.get("research", {}).get("unlocked", [])
    return [key for key, region in config.REGIONS.items() if not region["requires"] or region["requires"] in unlocked]


def travel(state, region_key):
    """Move colony operations to an unlocked region after paying travel energy."""
    region = config.REGIONS.get(region_key)
    if not region:
        return False, "Unknown region."
    if region_key not in available_regions(state):
        return False, f"Research is required to reach {region['name']}."
    resources = state.get("resources", {})
    if any(resources.get(key, 0) < amount for key, amount in region["travel_cost"].items()):
        return False, "Insufficient energy for regional travel."
    for key, amount in region["travel_cost"].items():
        resources[key] -= amount
    state["current_region"] = region_key
    if region_key not in state.setdefault("discovered_regions", []):
        state["discovered_regions"].append(region_key)
        state.setdefault("run_stats", {}).setdefault("regions_visited", 0)
        state["run_stats"]["regions_visited"] += 1
    return True, f"Operations moved to {region['name']}."


def scan_derelict(state):
    """Let a scout recover an artifact in the Derelict Zone exactly once."""
    if state.get("current_region") != "derelict_zone":
        return False, "Travel to the Derelict Zone first."
    if state.get("derelict_scanned"):
        return False, "This derelict site has already been recovered."
    if not any(drone.get("role") == "scout" for drone in state.get("drones", [])):
        return False, "Assign at least one Scout drone first."
    state["derelict_scanned"] = True
    state.setdefault("run_stats", {}).setdefault("artifacts_recovered", 0)
    state["run_stats"]["artifacts_recovered"] += 1
    state["research_points"] = state.get("research_points", 0) + 25
    state.setdefault("resources", {})["electronics"] = state["resources"].get("electronics", 0) + 3
    state["resources"]["components"] = state["resources"].get("components", 0) + 5
    return True, "Artifact recovered: +25 research points, +3 Electronics, +5 Components."


def update_trade_routes(state):
    """Offer premium contracts periodically while trade operations are available."""
    has_trade_route = "planetary_trade_routes" in state.get("research", {}).get("unlocked", [])
    in_trade_region = state.get("current_region") == "gas_giant_orbit"
    if not (has_trade_route and in_trade_region):
        return None
    if state.get("tick", 0) % 600 != 0 or state.get("tick", 0) == 0:
        return None
    offered, message = contracts.offer_premium_contract(state, template_index=state.get("tick", 0) // 600)
    return message if offered else None


def milestones(state):
    """Expose visible colony goals derived from progression systems."""
    completed = set(state.get("milestones", []))
    goals = {
        "deep_outpost": "deep_belt_outpost" in state.get("modules", []),
        "aurelia_trade": "orbital_trade_hub" in state.get("modules", []),
        "artifact_recovery": state.get("derelict_scanned", False),
        "industrial_colony": state.get("population", 0) >= 20 and sum(state.get("machines", {}).values()) >= 6,
    }
    for key, reached in goals.items():
        if reached:
            completed.add(key)
    state["milestones"] = sorted(completed)
    return state["milestones"]


MILESTONE_REWARDS = {
    "deep_outpost": {"name": "Deep-Belt Charter", "resources": {"platinum": 8, "electronics": 2}, "research_points": 10},
    "aurelia_trade": {"name": "Aurelia Trade Dividend", "resources": {"gold": 35, "silver": 20}, "research_points": 8},
    "artifact_recovery": {"name": "Artifact Archive", "resources": {"components": 6}, "research_points": 20},
    "industrial_colony": {"name": "Colony Expansion Grant", "resources": {"iron": 100, "ice": 100}, "research_points": 25},
}


def claim_milestone(state, milestone_key):
    """Claim a milestone once and add its economic and research rewards."""
    if milestone_key not in state.get("milestones", []):
        return False, "That colony milestone has not been reached."
    claimed = state.setdefault("claimed_milestones", [])
    if milestone_key in claimed:
        return False, "That milestone reward has already been claimed."
    reward = MILESTONE_REWARDS.get(milestone_key)
    if not reward:
        return False, "Unknown milestone reward."
    resources = state.setdefault("resources", {})
    for key, amount in reward["resources"].items():
        resources[key] = resources.get(key, 0) + amount
    state["research_points"] = state.get("research_points", 0) + reward["research_points"]
    claimed.append(milestone_key)
    return True, f"Claimed {reward['name']}."
