"""Toggleable region map and mission board for colony progression."""

from ursina import Button, Entity, Text, Vec3, camera, color, destroy
from .. import config, contracts, regions


def create_mission_board(app_ref):
    elements = []
    panel = Entity(parent=camera.ui, model="quad", color=color.rgba(10, 16, 28, 0.97), scale=(0.86, 0.82), position=Vec3(0, 0, -0.3), enabled=False)
    elements.append(panel)
    title = Text(text="REGION MAP & MISSION BOARD", parent=camera.ui, position=Vec3(-0.37, 0.35, -0.31), scale=1.15, color=color.azure, enabled=False)
    elements.append(title)
    subtitle = Text(text="", parent=camera.ui, position=Vec3(-0.37, 0.30, -0.31), scale=0.62, origin=(-0.5, 0), enabled=False)
    elements.append(subtitle)
    objective_text = Text(text="", parent=camera.ui, position=Vec3(-0.37, -0.12, -0.31), scale=0.58, origin=(-0.5, 0), enabled=False)
    elements.append(objective_text)
    close_button = Button(text="Close Map", parent=camera.ui, position=Vec3(0.32, 0.35, -0.31), scale=(0.14, 0.04), color=color.rgb(110, 35, 45), enabled=False)
    elements.append(close_button)
    claim_button = Button(text="Claim Next Reward", parent=camera.ui, position=Vec3(0.22, -0.26, -0.31), scale=(0.28, 0.045), color=color.rgb(35, 95, 70), enabled=False)
    elements.append(claim_button)
    contract_button = Button(text="Complete First Contract", parent=camera.ui, position=Vec3(-0.10, -0.26, -0.31), scale=(0.28, 0.045), color=color.rgb(35, 65, 110), enabled=False)
    elements.append(contract_button)

    cards = {}
    positions = [(-0.28, 0.16), (0.0, 0.16), (0.28, 0.16), (-0.14, 0.03), (0.14, 0.03)]
    for (region_key, region), (x, y) in zip(config.REGIONS.items(), positions):
        card = Button(text=region["name"], parent=camera.ui, position=Vec3(x, y, -0.31), scale=(0.24, 0.10), color=color.rgb(55, 60, 70), enabled=False)
        cards[region_key] = card
        elements.append(card)

        def travel(target=region_key):
            success, message = regions.travel(app_ref.state, target)
            if success:
                app_ref.change_region_visuals(target)
            subtitle.text = message
            refresh()

        card.on_click = travel

    def mission_summary():
        region_key = app_ref.state.get("current_region", "inner_belt")
        region = config.REGIONS[region_key]
        lines = [f"CURRENT REGION: {region['name']}", region["description"]]
        if region_key == "derelict_zone":
            lines.append("OBJECTIVE: Scan the derelict with a Scout drone." if not app_ref.state.get("derelict_scanned") else "OBJECTIVE COMPLETE: Artifact archive recovered.")
        elif region_key == "gas_giant_orbit":
            lines.append("OBJECTIVE: Complete premium Aurelia trade contracts.")
        elif region_key == "deep_belt":
            lines.append("OBJECTIVE: Build a Deep-Belt Outpost.")
        else:
            lines.append("OBJECTIVE: Research logistics, deepen automation, and unlock the next route.")
        active = app_ref.state.get("contracts", {}).get("active", [])
        if active:
            lines.append("ACTIVE CONTRACT: " + active[0]["title"])
        milestones = app_ref.state.get("milestones", [])
        claimed = app_ref.state.get("claimed_milestones", [])
        claimable = [key for key in milestones if key not in claimed]
        if claimable:
            lines.append("CLAIMABLE MILESTONE: " + regions.MILESTONE_REWARDS[claimable[0]]["name"])
        return "\n".join(lines), claimable

    def refresh():
        available = regions.available_regions(app_ref.state)
        current = app_ref.state.get("current_region", "inner_belt")
        for region_key, card in cards.items():
            unlocked = region_key in available
            card.enabled = panel.enabled and unlocked
            card.color = color.azure if region_key == current else color.rgb(35, 65, 110) if unlocked else color.rgb(55, 60, 70)
            suffix = "" if unlocked else "\nLOCKED"
            card.text = config.REGIONS[region_key]["name"] + suffix
        summary, claimable = mission_summary()
        objective_text.text = summary
        claim_button.enabled = panel.enabled and bool(claimable)
        claim_button.text = "Claim: " + regions.MILESTONE_REWARDS[claimable[0]]["name"] if claimable else "No Reward Available"
        active = app_ref.state.get("contracts", {}).get("active", [])
        contract_button.enabled = panel.enabled and bool(active)
        contract_button.text = "Complete: " + active[0]["title"] if active else "No Active Contract"

    def toggle():
        visible = not panel.enabled
        for element in elements:
            element.enabled = visible
        if visible:
            refresh()

    def claim_next():
        _, message = regions.claim_milestone(app_ref.state, next((key for key in app_ref.state.get("milestones", []) if key not in app_ref.state.get("claimed_milestones", [])), ""))
        subtitle.text = message
        refresh()

    def complete_contract():
        active = app_ref.state.get("contracts", {}).get("active", [])
        if active:
            _, subtitle.text = contracts.complete_contract(app_ref.state, active[0]["title"])
        refresh()

    close_button.on_click = toggle
    claim_button.on_click = claim_next
    contract_button.on_click = complete_contract
    return {"toggle": toggle, "refresh": refresh, "panel": panel}
