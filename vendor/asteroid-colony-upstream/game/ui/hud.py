"""In-game HUD for resources, colony alerts, and operational status."""

from ursina import Entity, Text, Vec3, camera, color
from .. import config, i18n, logistics


def create_hud(game_manager):
    hud_bg = Entity(parent=camera.ui, model="quad", color=color.rgba(20, 25, 35, 0.88), scale=(1.0, 0.16), position=Vec3(0, 0.41, 0), collider="box")
    res_texts = {}
    for index, (key, info) in enumerate(config.RESOURCES.items()):
        if key == "energy":
            continue
        row, column = divmod(index, 5)
        x_pos = -0.46 + column * 0.18
        y_pos = 0.39 - row * 0.055
        Entity(parent=camera.ui, model="circle", color=color.rgb(*info["color"]), scale=0.018, position=Vec3(x_pos, y_pos, -0.1))
        res_texts[key] = Text(text=f"{info['name']}: 0", parent=camera.ui, position=Vec3(x_pos + 0.015, y_pos - 0.01, -0.1), scale=0.66, origin=(-0.5, 0))

    energy_text = Text(text=f"{i18n.t('energy', game_manager.lang)}: 0", parent=camera.ui, position=Vec3(0.31, 0.40, -0.1), scale=0.76, origin=(-0.5, 0))
    pop_text = Text(text=f"{i18n.t('population', game_manager.lang)}: 0", parent=camera.ui, position=Vec3(0.31, 0.35, -0.1), scale=0.76, origin=(-0.5, 0))
    storage_label = Text(text="Storage", parent=camera.ui, position=Vec3(0.31, 0.30, -0.1), scale=0.65, origin=(-0.5, 0))
    storage_bar = Entity(parent=camera.ui, model="quad", color=color.azure, scale=(0.18, 0.012), position=Vec3(0.40, 0.305, -0.1), origin=(-0.5, 0))
    production_text = Text(text="", parent=camera.ui, position=Vec3(0.31, 0.26, -0.1), scale=0.54, origin=(-0.5, 0), color=color.cyan)
    event_text = Text(text="", parent=camera.ui, position=Vec3(0, 0.20, -0.1), scale=0.85, origin=(0, 0))
    selected_text = Text(text="", parent=camera.ui, position=Vec3(0, -0.35, -0.1), scale=0.9, origin=(0, 0), color=color.yellow)
    return {"res_texts": res_texts, "energy_text": energy_text, "pop_text": pop_text, "storage_label": storage_label, "storage_bar": storage_bar, "production_text": production_text, "event_text": event_text, "selected_text": selected_text, "bg": hud_bg}


def update_hud(hud_elements, state, lang="en"):
    for key, text in hud_elements["res_texts"].items():
        value = state.get("resources", {}).get(key, 0)
        text.text = f"{config.RESOURCES.get(key, {}).get('name', key)}: {int(value)}"
        text.color = color.red if value < 10 else color.white

    energy = state.get("resources", {}).get("energy", 0)
    hud_elements["energy_text"].text = f"{i18n.t('energy', lang)}: {int(energy)}"
    hud_elements["energy_text"].color = color.yellow if energy < 5 else color.white
    hud_elements["pop_text"].text = f"{i18n.t('population', lang)}: {state.get('population', 0)}"

    summary = logistics.summary(state)
    ratio = min(1.0, summary["used"] / max(1, summary["capacity"]))
    hud_elements["storage_label"].text = f"Storage: {int(summary['used'])}/{int(summary['capacity'])}"
    hud_elements["storage_bar"].scale_x = 0.18 * ratio
    hud_elements["storage_bar"].color = color.red if ratio > 0.9 else color.orange if ratio > 0.7 else color.azure
    production = state.get("logistics", {}).get("production", {})
    if production:
        hud_elements["production_text"].text = "Production: " + " | ".join(f"{key.title()} {value}" for key, value in production.items())
    else:
        hud_elements["production_text"].text = "Production: waiting for modules"

    active_events = state.get("events_active", [])
    if active_events:
        hud_elements["event_text"].text = "! " + " | ".join(event.get("key", "").replace("_", " ").title() for event in active_events)
        hud_elements["event_text"].color = color.orange
    else:
        hud_elements["event_text"].text = ""
