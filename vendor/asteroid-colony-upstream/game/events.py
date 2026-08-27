"""Random economic events and their state effects."""

import random

EVENT_TYPES = [
    {"key": "meteor_shower", "name": "Meteor Shower", "duration": 10, "damage": 5},
    {"key": "solar_storm", "name": "Solar Storm", "duration": 15, "energy_penalty": 5},
    {"key": "trade_fleet", "name": "Trade Fleet", "duration": 12, "bonus": {"gold": 15}},
    {"key": "gold_rush", "name": "Gold Rush", "duration": 8, "bonus": {"gold": 30, "platinum": 10}},
]

def roll_event(state, tick_interval=300):
    """Possibly add a time-limited event based on the current difficulty."""
    if state.get("tick", 0) % tick_interval == 0 and state.get("tick", 0) > 0:
        factor = state.get("difficulty_factor", 1.0)
        if random.random() < 0.15 * factor:
            event = random.choice(EVENT_TYPES).copy()
            event["start_tick"] = state.get("tick", 0)
            event["end_tick"] = event["start_tick"] + event.get("duration", 10)
            state.setdefault("events_active", []).append(event)

def apply_events(state):
    """Apply active event effects and remove expired events."""
    active = state.get("events_active", [])
    tick = state.get("tick", 0)
    expired = []
    for event in active:
        if tick >= event.get("end_tick", 0):
            expired.append(event)
        elif event["key"] == "solar_storm":
            state["resources"]["energy"] -= event.get("energy_penalty", 5) / 60
        elif event["key"] == "meteor_shower" and not state.get("shield_active", False):
            state["resources"]["energy"] -= event.get("damage", 5) / 60
    for event in expired:
        active.remove(event)

def event_description(event_obj, lang="en"):
    """Return the event's English display name; `lang` remains API-compatible."""
    key = event_obj.get("key", "")
    for event in EVENT_TYPES:
        if event["key"] == key:
            return event["name"]
    return key

EVENT_CHOICES = {
    "solar_storm": {
        "shield": {"name": "Divert power to shields", "cost": {"energy": 4}, "effect": "prevent_damage"},
        "endure": {"name": "Keep production online", "effect": "accept_damage"},
    },
    "trade_fleet": {
        "sell_iron": {"name": "Sell 25 Iron", "cost": {"iron": 25}, "reward": {"gold": 20}},
        "decline": {"name": "Decline the offer", "effect": "none"},
    },
}


def resolve_event_choice(state, event_key, choice_key):
    """Resolve a player decision for an active event."""
    choice = EVENT_CHOICES.get(event_key, {}).get(choice_key)
    if not any(event.get("key") == event_key for event in state.get("events_active", [])):
        return False, "That event is not currently active."
    if choice is None:
        return False, "That event choice is unavailable."
    resources = state.get("resources", {})
    if not all(resources.get(key, 0) >= amount for key, amount in choice.get("cost", {}).items()):
        return False, "Insufficient resources for that decision."
    for key, amount in choice.get("cost", {}).items():
        resources[key] -= amount
    for key, amount in choice.get("reward", {}).items():
        resources[key] = resources.get(key, 0) + amount
    if choice.get("effect") == "prevent_damage":
        state["shield_active"] = True
    return True, f"Decision accepted: {choice['name']}."
