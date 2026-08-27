# game/ui/build_menu.py — Build Menu
from ursina import *
from .. import config, economy, i18n

def create_build_menu(app_ref):
    panel = Entity(
        parent=camera.ui,
        model='quad',
        color=color.rgba(30, 35, 45, 0.9),
        scale=(0.35, 0.45),
        position=Vec3(-0.42, -0.25, -0.2),
    )
    title = Text(
        text=i18n.t("build_module", app_ref.lang),
        parent=camera.ui,
        position=Vec3(-0.35, 0.3, -0.2),
        scale=1.0,
    )
    # Basic drone button.
    btn_drone = Button(
        text=i18n.t("build_drone", app_ref.lang),
        parent=camera.ui,
        position=Vec3(-0.35, 0.15, -0.2),
        scale=(0.28, 0.05),
        color=color.rgb(35, 65, 110),
        on_click=lambda: build_drone(app_ref),
    )
    # Simple module selection.
    btn_mod1 = Button(
        text=f"{i18n.t('modules', app_ref.lang)}",
        parent=camera.ui,
        position=Vec3(-0.35, 0.0, -0.2),
        scale=(0.28, 0.05),
        color=color.rgb(55, 60, 70),
        on_click=lambda: show_module_select(app_ref),
    )

def build_drone(app_ref):
    state = app_ref.state
    drone_state_template = state.get("drones", [{}])[0] if state.get("drones") else {}
    cost = economy.drone_cost({"id": len(state.get("drones", [])) + 1})
    from .. import state as st_mod
    if st_mod.resource_ok(state, cost, factor=1.0):
        st_mod.deduct_resources(state, cost, factor=1.0)
        new_id = max([d["id"] for d in state["drones"]], default=0) + 1
        state["drones"].append({
            "id": new_id,
            "level_speed": 0,
            "level_cargo": 0,
            "level_mining": 0,
            "state": "idle",
            "target": None,
            "cargo": 0,
            "health": 1.0,
            "role": "miner",
        })
        # Add the visual drone in main.py, which owns the scene.
        if hasattr(app_ref, 'add_new_drone'):
            app_ref.add_new_drone(new_id)
        print("[Build] Drone built.")
    else:
        print("[Build] Not enough resources for a drone.")

def show_module_select(app_ref):
    # Build a random available module.
    st = app_ref.state
    unlocked = st.get("research", {}).get("unlocked", [])
    available = [key for key, info in config.MODULES.items() if key not in st.get("modules", []) and (not info.get("requires_research") or info["requires_research"] in unlocked)]
    if not available:
        print("[Build] No new modules available (maximum two of each).")
        return
    # For the demo, build the first available module.
    mod_key = available[0]
    info = config.MODULES[mod_key]
    cost = info.get("cost", {})
    if st.get("resources") and all(st["resources"].get(k, 0) >= v for k, v in cost.items()):
        for k, v in cost.items():
            st["resources"][k] -= v
        st.setdefault("modules", []).append(mod_key)
        print(f"[Build] Module built: {info.get('name', mod_key)}")
    else:
        print("[Build] Not enough resources for a module.")
