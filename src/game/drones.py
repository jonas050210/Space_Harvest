"""Drone-role assignment and autonomous mining behavior."""

from . import config, entities


def role_profile(drone_state):
    """Return the configured profile for a drone's role."""
    return config.DRONE_ROLES.get(drone_state.get("role", "miner"), config.DRONE_ROLES["miner"])


def assign_role(state, drone_id, role):
    """Assign a specialized role to a drone after specialization is researched."""
    if role not in config.DRONE_ROLES:
        return False, "Unknown drone role."
    if "drone_specialization" not in state.get("research", {}).get("unlocked", []):
        return False, "Research Drone Specialization first."
    drone = next((item for item in state.get("drones", []) if item.get("id") == drone_id), None)
    if drone is None:
        return False, "Drone not found."
    drone["role"] = role
    return True, f"Drone {drone_id} assigned as {config.DRONE_ROLES[role]['name']}."


def _target_priority(asteroid, station_entity, role):
    distance = (station_entity.position - asteroid.position).length()
    value = config.RESOURCES.get(asteroid.res_type, {}).get("value", 1)
    if role == "miner":
        return value * 1.5 / max(distance, 1)
    if role == "hauler":
        return asteroid.amount / max(distance, 1)
    # Scouts intentionally favor distant, valuable asteroids.
    return value * distance


def _find_target(asteroids, station_entity, role):
    eligible = [asteroid for asteroid in asteroids if asteroid.amount > 5 and isinstance(asteroid, entities.Asteroid)]
    return max(eligible, key=lambda asteroid: _target_priority(asteroid, station_entity, role), default=None)


def drone_ai_step(drone_entity, drone_state, asteroids, station_entity, dt=0.016):
    """Advance one drone and return a delivery dictionary when it reaches the station."""
    role = drone_state.get("role", "miner")
    profile = role_profile(drone_state)
    speed = 2.0 + drone_state.get("level_speed", 0) * 0.8
    cargo_cap = (10 + drone_state.get("level_cargo", 0) * 8) * profile.get("cargo_multiplier", 1.0)
    mining_rate = (1 + drone_state.get("level_mining", 0) * 0.5) * profile.get("mining_multiplier", 1.0)

    if drone_state.get("target") is None and drone_state.get("state") == "idle":
        target = _find_target(asteroids, station_entity, role)
        if target is not None:
            drone_state.update({
                "target": target.res_type,
                "target_entity": target,
                "state": "flying_to",
                "cargo": 0,
                "cargo_resource": target.res_type,
            })
            drone_entity.target = target

    state_name = drone_state.get("state", "idle")
    target = drone_state.get("target_entity")
    if state_name == "flying_to" and target is not None:
        direction = target.position - drone_entity.position
        if direction.length() < 1.2:
            drone_state["state"] = "mining"
            drone_state["mine_timer"] = 3.0
            target.scanned = True
            drone_entity.beam.enabled = True
            drone_entity.beam.look_at(target)
        else:
            drone_entity.position += direction.normalize() * speed * dt
            drone_entity.look_at(target.position)

    elif state_name == "mining" and target is not None:
        mined = min(mining_rate * dt, max(0, target.amount), max(0, cargo_cap - drone_state.get("cargo", 0)))
        target.amount -= mined
        drone_state["cargo"] = drone_state.get("cargo", 0) + mined
        drone_state["mine_timer"] = drone_state.get("mine_timer", 0) - dt
        if drone_state["mine_timer"] <= 0 or target.amount <= 0 or drone_state["cargo"] >= cargo_cap:
            drone_state["state"] = "returning"
            drone_state["target_entity"] = None
            drone_state["target"] = None
            drone_entity.beam.enabled = False
            drone_entity.target = station_entity

    elif state_name == "returning":
        direction = station_entity.position - drone_entity.position
        return_speed = speed * profile.get("return_speed_multiplier", 1.0)
        if direction.length() < 1.5:
            delivery = {drone_state.get("cargo_resource"): drone_state.get("cargo", 0)}
            drone_state.update({"state": "idle", "target_entity": None, "target": None})
            return {key: value for key, value in delivery.items() if key and value > 0}
        drone_entity.position += direction.normalize() * return_speed * dt
        drone_entity.look_at(station_entity.position)

    if hasattr(drone_entity, "label"):
        drone_entity.label.text = f"D{drone_state['id']} {role[:1].upper()}\n{int(drone_state.get('cargo', 0))}/{int(cargo_cap)}"
    return {}
