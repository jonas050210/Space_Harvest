# Machines and upgrades with increasing tycoon-style prices.
from ursina import *
from .. import i18n, config, state as st_mod

def create_tech_menu(app_ref):
    overlay = Entity(
        parent=camera.ui,
        model='quad',
        color=color.rgba(30, 25, 20, 0.9),
        scale=(0.6, 0.55),
        position=Vec3(0.35, 0.05, -0.2),
    )
    title = Text(
        text="Machines & Upgrades",
        parent=camera.ui,
        position=Vec3(0.35, 0.28, -0.2),
        scale=1.1,
        color=color.yellow,
    )
    # Machine buttons with dynamic prices.
    btn_mining_drill = Button(
        text="Mining Drill (price increases!)",
        parent=camera.ui,
        position=Vec3(0.35, 0.15, -0.2),
        scale=(0.35, 0.05),
        color=color.rgb(35, 65, 110),
        on_click=lambda: buy_machine(app_ref, "mining_drill"),
    )
    btn_refinery = Button(
        text="Mini Refinery (price increases!)",
        parent=camera.ui,
        position=Vec3(0.35, 0.05, -0.2),
        scale=(0.35, 0.05),
        color=color.rgb(35, 65, 110),
        on_click=lambda: buy_machine(app_ref, "refinery"),
    )
    btn_transporter = Button(
        text="Auto Transporter (price increases!)",
        parent=camera.ui,
        position=Vec3(0.35, -0.05, -0.2),
        scale=(0.35, 0.05),
        color=color.rgb(35, 65, 110),
        on_click=lambda: buy_machine(app_ref, "auto_transporter"),
    )
    # Dynamic price label.
    price_text = Text(
        text="",
        parent=camera.ui,
        position=Vec3(0.35, -0.18, -0.2),
        scale=0.8,
        color=color.orange,
        origin=(-0.5, 0),
    )

def buy_machine(app_ref, key):
    cost = st_mod.get_machine_cost(key, app_ref.state)
    if not cost:
        print("[Machines] Unknown machine.")
        return
    if st_mod.resource_ok(app_ref.state, cost):
        st_mod.deduct_resources(app_ref.state, cost)
        current = app_ref.state.get("machines", {}).get(key, 0)
        app_ref.state.setdefault("machines", {})[key] = current + 1
        print(f"[Machines] Purchased: {config.MACHINES[key].get('name', key)} (now {current + 1}x)")
    else:
        print(f"[Machines] Not enough resources for {key}. Required: {cost}")
