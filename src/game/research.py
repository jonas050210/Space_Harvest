"""Research progression and unlock validation."""

from . import config


def unlocked(state, research_key):
    """Return whether a research item has been completed."""
    return research_key in state.get("research", {}).get("unlocked", [])


def available_research(state):
    """Return research entries whose prerequisites are complete."""
    return [
        key for key, item in config.RESEARCH.items()
        if not unlocked(state, key)
        and all(unlocked(state, prerequisite) for prerequisite in item["requires"])
    ]


def can_research(state, research_key):
    """Validate a research purchase without modifying state."""
    item = config.RESEARCH.get(research_key)
    return bool(
        item
        and research_key in available_research(state)
        and state.get("research_points", 0) >= item["cost"]
    )


def unlock(state, research_key):
    """Spend research points and unlock a technology. Returns success and a message."""
    if research_key not in config.RESEARCH:
        return False, "Unknown research item."
    if unlocked(state, research_key):
        return False, "Research already completed."
    if research_key not in available_research(state):
        return False, "Research prerequisites are not complete."
    cost = config.RESEARCH[research_key]["cost"]
    if state.get("research_points", 0) < cost:
        return False, f"Need {cost} research points."
    state["research_points"] -= cost
    state.setdefault("research", {}).setdefault("unlocked", []).append(research_key)
    return True, f"Research completed: {config.RESEARCH[research_key]['name']}"


def generate_points(state, dt):
    """Generate research points from colonists and research-capable infrastructure."""
    multiplier = 1.0 + 0.15 * state.get("machines", {}).get("refinery", 0)
    multiplier += 0.4 * state.get("modules", []).count("research_observatory")
    if unlocked(state, "deep_space_scanning"):
        multiplier += 0.1
    state["research_points"] = state.get("research_points", 0.0) + (
        (0.025 + state.get("population", 0) * 0.004) * multiplier * dt
    )
