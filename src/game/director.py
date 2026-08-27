"""Colony Director: player-facing objectives, alerts, and recommendations."""

from . import config, logistics, research


def _active_contract_progress(state):
    active = state.get("contracts", {}).get("active", [])
    if not active:
        return None
    contract = active[0]
    resources = state.get("resources", {})
    required = sum(contract["requirements"].values())
    delivered = sum(min(resources.get(key, 0), amount) for key, amount in contract["requirements"].items())
    return {"title": contract["title"], "progress": delivered / max(1, required), "requirements": contract["requirements"]}


def alerts(state):
    """Return operational warnings in descending urgency."""
    result = []
    resources = state.get("resources", {})
    if resources.get("energy", 0) < 8:
        result.append(("critical", "Energy reserve is low. Build Solar Panels or pause energy-heavy expansion."))
    storage = logistics.summary(state)
    ratio = storage["used"] / max(1, storage["capacity"])
    if ratio > 0.9:
        result.append(("critical", "Storage is almost full. Build Storage, refine materials, or complete a contract."))
    elif ratio > 0.7:
        result.append(("warning", "Storage is filling. Plan a delivery, production run, or expansion."))
    if state.get("current_region") == "derelict_zone" and not state.get("derelict_scanned"):
        if not any(drone.get("role") == "scout" for drone in state.get("drones", [])):
            result.append(("warning", "Derelict Zone requires a Scout drone assignment."))
        else:
            result.append(("opportunity", "A Scout can recover the derelict artifact now."))
    if state.get("contracts", {}).get("active"):
        progress = _active_contract_progress(state)
        if progress and progress["progress"] >= 1:
            result.append(("opportunity", f"Contract ready to complete: {progress['title']}."))
    return result


def objective(state):
    """Choose one clear goal from the colony's current progression state."""
    unlocked = state.get("research", {}).get("unlocked", [])
    region = state.get("current_region", "inner_belt")
    if region == "derelict_zone" and not state.get("derelict_scanned"):
        return "Recover the Derelict Zone artifact with a Scout drone."
    if "drone_specialization" not in unlocked:
        return "Research Drone Specialization and assign dedicated colony roles."
    if "deep_space_scanning" not in unlocked:
        return "Research Deep-Space Scanning to reach rare-metal operations."
    if "planetary_trade_routes" not in unlocked:
        return "Research Planetary Trade Routes to unlock Aurelia premium contracts."
    if "deep_belt_outpost" not in state.get("modules", []):
        return "Build a Deep-Belt Outpost to establish long-range operations."
    return "Expand industrial capacity, complete premium contracts, and claim colony milestones."


def recommendation(state):
    """Provide the single best practical next action."""
    current_alerts = alerts(state)
    if current_alerts:
        return current_alerts[0][1]
    next_research = research.available_research(state)
    if next_research:
        item = config.RESEARCH[next_research[0]]
        points = int(state.get("research_points", 0))
        if points >= item["cost"]:
            return f"Research {item['name']} now."
        return f"Generate research points for {item['name']} ({points}/{item['cost']} RP)."
    contract = _active_contract_progress(state)
    if contract:
        return f"Prioritize resources for {contract['title']}."
    return "Assign drones by role and use the Region Map to pursue the next milestone."


def snapshot(state):
    """Return a compact, UI-ready operational summary."""
    contract = _active_contract_progress(state)
    return {
        "objective": objective(state),
        "recommendation": recommendation(state),
        "alerts": alerts(state),
        "contract": contract,
        "region": config.REGIONS[state.get("current_region", "inner_belt")]["name"],
        "milestones": len(state.get("milestones", [])),
    }
