# Main and in-game menus.
from ursina import *
from .. import i18n, settings, savegame, config

def create_main_menu(app_ref):
    # Hintergrund easy abgedunkelt
    overlay = Entity(
        parent=camera.ui,
        model='quad',
        color=color.rgba(10, 15, 25, 0.7),
        scale=(1.2, 1.2),
        position=Vec3(0, 0, 0),
        enabled=False,
    )
    title_text = Text(
        text=i18n.t("title", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(0, 0.15, 0),
        scale=2.5,
        color=color.yellow,
        enabled=False,
    )

    def resume():
        overlay.enabled = False
        title_text.enabled = False
        for btn in btns.values():
            btn.enabled = False
        app_ref.paused = False

    def open_settings():
        create_settings_menu(app_ref, resume_callback=lambda: open_main_menu(app_ref))

    def open_main_menu(app_ref):
        overlay.enabled = True
        title_text.enabled = True
        for btn in btns.values():
            btn.enabled = True
        app_ref.paused = True

    btns = {}
    btns["resume"] = Button(
        text=i18n.t("resume", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(0, 0.02, -0.1),
        scale=(0.25, 0.06),
        color=color.rgb(55, 60, 70),
        on_click=resume,
        enabled=False,
    )
    btns["save"] = Button(
        text=i18n.t("save", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(-0.25, -0.08, -0.1),
        scale=(0.2, 0.06),
        color=color.rgb(35, 65, 110),
        on_click=lambda: save_current(app_ref),
        enabled=False,
    )
    btns["load"] = Button(
        text=i18n.t("load", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(0.25, -0.08, -0.1),
        scale=(0.2, 0.06),
        color=color.rgb(35, 65, 110),
        on_click=lambda: load_current(app_ref),
        enabled=False,
    )
    btns["settings"] = Button(
        text=i18n.t("settings", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(-0.25, -0.18, -0.1),
        scale=(0.2, 0.06),
        color=color.rgb(55, 60, 70),
        on_click=open_settings,
        enabled=False,
    )
    btns["quit"] = Button(
        text=i18n.t("quit", settings.load().get("language", "en")),
        parent=camera.ui,
        position=Vec3(0.25, -0.18, -0.1),
        scale=(0.2, 0.06),
        color=color.rgb(110, 35, 45),
        on_click=application.quit,
        enabled=False,
    )

    # Save and load logic.
    def save_current(app_ref):
        from . import menu
        # Save the current game in the saves directory.
        st = app_ref.state if hasattr(app_ref, 'state') else {}
        if st:
            savegame.save_slot("autosave_" + str(int(time.time())), st)
            print("[Menu] Saved.")
    def load_current(app_ref):
        saves = savegame.list_saves()
        if saves:
            data = savegame.load_slot(saves[0].replace(".json", ""))
            if data and hasattr(app_ref, 'load_state'):
                app_ref.load_state(data)
                print("[Menu] Loaded:", saves[0])

    return open_main_menu, btns, overlay, title_text

def create_settings_menu(app_ref, resume_callback):
    """Show the English-only settings confirmation panel."""
    overlay = Entity(parent=camera.ui, model='quad', color=color.rgba(15, 20, 30, 0.9), scale=(0.7, 0.7), position=Vec3(0, 0, 0))
    label = Text(text="Language: English", parent=camera.ui, position=Vec3(0, 0.15, -0.1), scale=1.2)
    status = Text(text="English is the project language.", parent=camera.ui, position=Vec3(0, 0.05, -0.1), scale=0.8)
    back = Button(text="Back", parent=camera.ui, position=Vec3(0, -0.15, -0.1), scale=(0.15, 0.06), color=color.rgb(35, 65, 110), on_click=lambda: (destroy(overlay), destroy(label), destroy(status), destroy(back), resume_callback()))


def set_lang(app_ref, lang="en"):
    """Retained for save compatibility; the project always uses English."""
    settings_data = settings.load()
    settings_data["language"] = "en"
    settings.save(settings_data)
    if hasattr(app_ref, 'lang'):
        app_ref.lang = "en"
    if hasattr(app_ref, 'hud_elements') and app_ref.hud_elements:
        from . import hud
        hud.update_hud(app_ref.hud_elements, app_ref.state, "en")
    print("[Menu] Language: English")
