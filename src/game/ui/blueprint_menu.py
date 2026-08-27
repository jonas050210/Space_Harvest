# Blueprint menu for saving and loading station layouts.
from ursina import *
from .. import blueprint

def create_blueprint_menu(app_ref):
    overlay = Entity(
        parent=camera.ui,
        model='quad',
        color=color.rgba(20, 15, 30, 0.92),
        scale=(0.7, 0.6),
        position=Vec3(-0.35, 0.0, -0.2),
    )
    title = Text(
        text="BLUEPRINTS — Station Design",
        parent=camera.ui,
        position=Vec3(-0.35, 0.28, -0.2),
        scale=1.0,
        color=color.yellow,
    )
    # Save button
    btn_save = Button(
        text="SAVE CURRENT DESIGN",
        parent=camera.ui,
        position=Vec3(-0.35, 0.15, -0.2),
        scale=(0.35, 0.05),
        color=color.rgb(35, 65, 110),
        on_click=lambda: save_current_blueprint(app_ref),
    )
    # Load button for the newest blueprint.
    btn_load = Button(
        text="LOAD LATEST BLUEPRINT",
        parent=camera.ui,
        position=Vec3(-0.35, 0.05, -0.2),
        scale=(0.35, 0.05),
        color=color.rgb(35, 95, 70),
        on_click=lambda: load_latest_blueprint(app_ref),
    )
    # List available blueprints.
    blueprint_text = Text(
        text="Available: " + ", ".join(blueprint.list_blueprints()[:3]),
        parent=camera.ui,
        position=Vec3(-0.35, -0.1, -0.2),
        scale=0.9,
        origin=(-0.5, 0),
        color=color.white,
    )

def save_current_blueprint(app_ref):
    # Collect data from the current game.
    asteroid_positions = getattr(app_ref, 'asteroids', [])
    drone_states = app_ref.state.get("drones", [])
    module_list = app_ref.state.get("modules", [])
    machine_counts = app_ref.state.get("machines", {})
    path = blueprint.save_blueprint(
        f"station_{int(app_ref.state.get('tick', 0))}",
        app_ref.state,
        asteroid_positions,
        drone_states,
        module_list,
        machine_counts,
    )
    print(f"[Blueprint] Design saved: {path}")

def load_latest_blueprint(app_ref):
    blueprints = blueprint.list_blueprints()
    if blueprints:
        latest = blueprints[0].replace(".json", "")
        blueprint.load_blueprint(latest, app_ref)
        print(f"[Blueprint] Design loaded: {latest}")
    else:
        print("[Blueprint] No saved designs found.")
