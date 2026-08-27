"""Command panel for research, roles, regions, contracts, and exploration."""

from ursina import Button, Entity, Text, Vec3, camera, color
from .. import config, contracts, drones, logistics, regions, research


def create_automation_menu(app_ref):
    panel = Entity(parent=camera.ui, model="quad", color=color.rgba(18, 28, 38, 0.94), scale=(0.40, 0.62), position=Vec3(0.58, -0.18, -0.2))
    Text(text="AUTOMATION COMMAND", parent=camera.ui, position=Vec3(0.43, 0.10, -0.2), scale=0.78, color=color.azure)
    status = Text(text="", parent=camera.ui, position=Vec3(0.43, -0.18, -0.2), scale=0.56, origin=(-0.5, 0))
    research_button = Button(text="Research", parent=camera.ui, position=Vec3(0.56, 0.04, -0.2), scale=(0.31, 0.042), color=color.rgb(35, 65, 110))
    role_button = Button(text="Assign Role", parent=camera.ui, position=Vec3(0.56, -0.015, -0.2), scale=(0.31, 0.042), color=color.rgb(55, 60, 70))
    placement_button = Button(text="Place Module", parent=camera.ui, position=Vec3(0.56, -0.07, -0.2), scale=(0.31, 0.042), color=color.rgb(55, 60, 70))
    region_button = Button(text="Travel", parent=camera.ui, position=Vec3(0.56, -0.125, -0.2), scale=(0.31, 0.042), color=color.rgb(145, 80, 220))
    contract_button = Button(text="Request Contract", parent=camera.ui, position=Vec3(0.56, -0.18, -0.2), scale=(0.31, 0.042), color=color.rgb(35, 95, 70))
    explore_button = Button(text="Scan Derelict", parent=camera.ui, position=Vec3(0.56, -0.235, -0.2), scale=(0.31, 0.042), color=color.orange)
    map_button = Button(text="Open Region Map", parent=camera.ui, position=Vec3(0.56, -0.29, -0.2), scale=(0.31, 0.042), color=color.azure)

    def research_next():
        available = research.available_research(app_ref.state)
        if not available:
            status.text = "All currently available research is complete."
            return
        _, status.text = research.unlock(app_ref.state, available[0])

    def assign_next_role():
        drone_list = app_ref.state.get("drones", [])
        if not drone_list:
            status.text = "No drones available."
            return
        index = app_ref.state.setdefault("automation_selection", 0) % len(drone_list)
        drone = drone_list[index]
        role_keys = list(config.DRONE_ROLES)
        next_role = role_keys[(role_keys.index(drone.get("role", "miner")) + 1) % len(role_keys)]
        success, message = drones.assign_role(app_ref.state, drone["id"], next_role)
        if success:
            app_ref.state["automation_selection"] += 1
        status.text = message

    def travel_next():
        options = regions.available_regions(app_ref.state)
        current = app_ref.state.get("current_region", "inner_belt")
        next_region = options[(options.index(current) + 1) % len(options)]
        success, message = regions.travel(app_ref.state, next_region)
        if success:
            app_ref.change_region_visuals(next_region)
        status.text = message

    def handle_contract():
        active = app_ref.state.get("contracts", {}).get("active", [])
        if active:
            _, status.text = contracts.complete_contract(app_ref.state, active[0]["title"])
        else:
            _, status.text = contracts.offer_contract(app_ref.state, app_ref.state.get("tick", 0))

    def explore_derelict():
        _, status.text = regions.scan_derelict(app_ref.state)

    research_button.on_click = research_next
    role_button.on_click = assign_next_role
    placement_button.on_click = lambda: app_ref.place_next_module()
    region_button.on_click = travel_next
    contract_button.on_click = handle_contract
    explore_button.on_click = explore_derelict
    map_button.on_click = lambda: app_ref.mission_board["toggle"]() if app_ref.mission_board else None

    def update_panel():
        points = int(app_ref.state.get("research_points", 0))
        summary = logistics.summary(app_ref.state)
        available = research.available_research(app_ref.state)
        next_name = config.RESEARCH[available[0]]["name"] if available else "Complete"
        research_button.text = f"Research: {next_name} ({points} RP)"
        role_button.text = "Unlock Drone Roles" if "drone_specialization" not in app_ref.state.get("research", {}).get("unlocked", []) else "Assign Next Drone Role"
        region_button.text = f"Travel: {config.REGIONS[app_ref.state.get('current_region', 'inner_belt')]['name']}"
        contract_button.text = "Complete First Contract" if app_ref.state.get("contracts", {}).get("active", []) else "Request Contract"
        explore_button.enabled = app_ref.state.get("current_region") == "derelict_zone"
        if not status.text:
            status.text = f"Storage {int(summary['used'])}/{int(summary['capacity'])} | Milestones {len(app_ref.state.get('milestones', []))}"

    return {"panel": panel, "status": status, "update": update_panel}
