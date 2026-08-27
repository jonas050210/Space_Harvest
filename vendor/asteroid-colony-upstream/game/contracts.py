"""Faction contracts, reputation, and player-driven economic choices."""

CONTRACT_TEMPLATES = [
    {"faction": "Helios Exchange", "title": "Ice Lifeline", "requirements": {"ice": 80}, "reward": {"gold": 18}, "reputation": 8},
    {"faction": "Ironclad Works", "title": "Foundry Supply", "requirements": {"iron": 100}, "reward": {"silver": 25}, "reputation": 10},
    {"faction": "Orion Research Guild", "title": "Precision Components", "requirements": {"components": 6}, "reward_research": 15, "reputation": 12},
]


def offer_contract(state, template_index=0):
    """Offer a contract once; duplicate active offers are avoided."""
    template = CONTRACT_TEMPLATES[template_index % len(CONTRACT_TEMPLATES)].copy()
    active = state.setdefault("contracts", {}).setdefault("active", [])
    if any(contract["title"] == template["title"] for contract in active):
        return False, "That contract is already active."
    active.append(template)
    return True, f"New contract: {template['title']} from {template['faction']}."


def complete_contract(state, title):
    """Deliver contract requirements, issue rewards, and raise faction reputation."""
    active = state.setdefault("contracts", {}).setdefault("active", [])
    contract = next((item for item in active if item["title"] == title), None)
    if contract is None:
        return False, "Contract not found."
    resources = state.get("resources", {})
    if not all(resources.get(key, 0) >= amount for key, amount in contract["requirements"].items()):
        return False, "Contract requirements are not available."
    for key, amount in contract["requirements"].items():
        resources[key] -= amount
    for key, amount in contract.get("reward", {}).items():
        resources[key] = resources.get(key, 0) + amount
    state["research_points"] = state.get("research_points", 0) + contract.get("reward_research", 0)
    reputation = state["contracts"].setdefault("reputation", {})
    reputation[contract["faction"]] = reputation.get(contract["faction"], 0) + contract["reputation"]
    active.remove(contract)
    state["contracts"].setdefault("completed", []).append(title)
    state.setdefault("run_stats", {}).setdefault("contracts_completed", 0)
    state["run_stats"]["contracts_completed"] += 1
    return True, f"Contract completed: {title}."

PREMIUM_CONTRACT_TEMPLATES = [
    {"faction": "Aurelia Mercantile", "title": "Aurelia Electronics Run", "requirements": {"electronics": 2, "components": 4}, "reward": {"platinum": 12, "gold": 30}, "reward_research": 8, "reputation": 18},
    {"faction": "Aurelia Mercantile", "title": "Orbital Water Reserve", "requirements": {"water": 24}, "reward": {"gold": 35, "silver": 20}, "reputation": 16},
]


def offer_premium_contract(state, template_index=0):
    """Offer a high-value contract unlocked by planetary trade research."""
    template = PREMIUM_CONTRACT_TEMPLATES[template_index % len(PREMIUM_CONTRACT_TEMPLATES)].copy()
    active = state.setdefault("contracts", {}).setdefault("active", [])
    if any(contract["title"] == template["title"] for contract in active):
        return False, "That premium contract is already active."
    active.append(template)
    return True, f"Premium contract received: {template['title']}."
