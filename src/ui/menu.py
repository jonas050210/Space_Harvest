"""Menu overlay - extracted from orbital_hud.py for maintainability.

This module owns title / pause / settings / howto / report screens.
Original implementation preserved, no behavior change.
"""

from __future__ import annotations


from src.app.controls import HOWTO_PAGES as CONTROL_HOWTO_PAGES
from src.config import (
    DEFAULT_SETTINGS,
    DIFFICULTY_MODES,
    DIFFICULTY_ORDER,
    FOV_ORDER,
    MASTER_VOLUME_STEPS,
    QUALITY_ORDER,
    RESOLUTION_ORDER,
    UI_SCALE_ORDER,
    VICTORY_MODES,
    VICTORY_ORDER,
    VIEW_MODES,
)

try:
    from ursina import Button, Entity, Text, color, window, camera
except Exception:  # pragma: no cover - headless
    Button = Entity = Text = None  # type: ignore
    color = window = camera = None  # type: ignore


class MenuOverlay:
    """Keyboard-navigable title / pause / settings / how-to-play screens.

    Kept inside the HUD module on purpose: same Ursina primitives, same
    styling, no second UI toolkit. ``handle(key)`` translates raw keys into
    semantic action tokens the Game layer executes.
    """

    MAIN_ITEMS = ("NEW HARVEST", "CONTINUE", "LOAD LAST SAVE", "SETTINGS", "HOW TO PLAY", "QUIT")
    PAUSE_ITEMS = ("RESUME", "SAVE", "YEAR REPORT", "SETTINGS", "QUIT TO TITLE")
    HOWTO_PAGES = CONTROL_HOWTO_PAGES

    # Settings rows: (settings-dict key, label, kind)
    # kind: cycle_list | toggle | cycle_num
    SETTINGS_ROWS = (
        ("quality", "Quality preset", "cycle_list", QUALITY_ORDER),
        ("view_mode", "Default view", "cycle_list", VIEW_MODES),
        ("resolution", "Resolution", "cycle_list", RESOLUTION_ORDER),
        ("fullscreen", "Fullscreen", "toggle", None),
        ("vsync", "VSync", "toggle", None),
        ("fov", "Field of view", "cycle_num", FOV_ORDER),
        ("ui_scale", "UI scale", "cycle_num", UI_SCALE_ORDER),
        ("master_volume", "Master volume", "cycle_num", MASTER_VOLUME_STEPS),
        ("muted", "Audio", "toggle_mute", None),
        ("glide", "Camera glide", "toggle", None),
        ("confirm_dispatch", "Confirm dispatch", "toggle", None),
        ("show_dossier", "Body dossier", "toggle", None),
        ("show_map_grid", "System map grid", "toggle", None),
        ("show_surface_hud", "Surface HUD", "toggle", None),
        ("drone_fx", "Drone swarm FX", "toggle", None),
        ("rival_enabled", "Rival charter", "toggle", None),
        ("show_route_overlay", "Route overlay", "toggle", None),
        ("ui_contrast", "High-contrast UI", "toggle", None),
        ("difficulty", "Difficulty", "cycle_list", DIFFICULTY_ORDER),
        ("victory", "Victory mode", "cycle_list", VICTORY_ORDER),
    )

    def __init__(self, continue_available: bool = False):
        self.screen = "main"          # main | settings | howto | pause | report
        self.cursor = 0
        self.howto_page = 0
        self.continue_available = continue_available
        self.settings = dict(DEFAULT_SETTINGS)
        self.on_settings_changed = None   # callable(dict) set by the game
        self._report_lines: list[str] = []

        self.panel = Entity(parent=camera.ui, model="quad",
                            color=color.rgba(0.02, 0.03, 0.06, 0.90),
                            scale=(0.9, 1.0), z=0.5)
        self.title = Text(text="SPACE HARVEST", parent=camera.ui,
                          position=(0.0, 0.30, -0.4), scale=2.4, origin=(0.0, 0),
                          color=color.rgb(0.5, 0.9, 1.0))
        self.subtitle = Text(text="wait for the window  --  harvest the belt  --  keep the colony alive",
                             parent=camera.ui, position=(0.0, 0.235, -0.4),
                             scale=0.7, origin=(0.0, 0), color=color.rgba(0.8, 0.88, 1.0, 0.9))
        self.items: list[Text] = [
            Text(text="", parent=camera.ui, position=(0.0, 0.10 - i * 0.05, -0.4),
                 scale=0.9, origin=(0.0, 0), color=color.white)
            for i in range(max(len(self.MAIN_ITEMS), len(self.PAUSE_ITEMS), 8))
        ]
        self.settings_lines = [
            Text(text="", parent=camera.ui, position=(0.0, 0.18 - i * 0.038, -0.4),
                 scale=0.72, origin=(0.0, 0), color=color.white)
            for i in range(len(self.SETTINGS_ROWS) + 1)
        ]
        self.howto_title = Text(text="", parent=camera.ui, position=(0.0, 0.24, -0.4),
                                scale=1.2, origin=(0.0, 0), color=color.yellow)
        self.howto_lines = [
            Text(text="", parent=camera.ui, position=(0.0, 0.14 - i * 0.048, -0.4),
                 scale=0.72, origin=(0.0, 0), color=color.rgba(0.9, 0.94, 1.0, 0.95))
            for i in range(9)
        ]
        self.footer = Text(text="W/S move   ENTER select   A/D cycle   ESC back", parent=camera.ui,
                           position=(0.0, -0.40, -0.4), scale=0.6, origin=(0.0, 0),
                           color=color.rgba(0.6, 0.7, 0.85, 0.9))
        self.show_main()

    # -- visibility ------------------------------------------------------------
    def _hide_all(self) -> None:
        self.panel.enabled = False
        self.title.enabled = self.subtitle.enabled = False
        for text in self.items + self.settings_lines + self.howto_lines:
            text.enabled = False
        self.howto_title.enabled = False
        self.footer.enabled = False

    def _show_shell(self) -> None:
        self.panel.enabled = True
        self.footer.enabled = True
        for text in self.items + self.settings_lines + self.howto_lines:
            text.enabled = False
        self.howto_title.enabled = False

    def show_main(self, continue_available: bool | None = None) -> None:
        self.screen = "main"
        if continue_available is not None:
            self.continue_available = continue_available
        self.cursor = 0
        self._show_shell()
        self.title.text = "SPACE HARVEST"
        self.subtitle.text = "wait for the window  --  harvest the belt  --  keep the colony alive"
        self.title.enabled = self.subtitle.enabled = True
        self._render_items(self.MAIN_ITEMS)

    def show_pause(self) -> None:
        self.screen = "pause"
        self.cursor = 0
        self._show_shell()
        self.title.text = "PAUSED"
        self.subtitle.text = "the fields keep moving"
        self.title.enabled = self.subtitle.enabled = True
        self._render_items(self.PAUSE_ITEMS)

    def show_settings(self, settings: dict) -> None:
        self.back_target = self.screen if self.screen in ("main", "pause") else "main"
        self.screen = "settings"
        self.cursor = 0
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings or {})
        self.settings = merged
        self._show_shell()
        self.title.text = "SETTINGS"
        self.subtitle.text = "A/D or ENTER cycles   --   changes apply instantly"
        self.title.enabled = self.subtitle.enabled = True
        self._render_settings()

    def show_howto(self, page: int = 0) -> None:
        self.back_target = self.screen if self.screen in ("main", "pause") else "main"
        self.screen = "howto"
        self.howto_page = page % len(self.HOWTO_PAGES)
        self._show_shell()
        heading, lines = self.HOWTO_PAGES[self.howto_page]
        self.howto_title.text = f"HOW TO PLAY  ({self.howto_page + 1}/{len(self.HOWTO_PAGES)})  --  {heading}"
        self.howto_title.enabled = True
        for i, text_entity in enumerate(self.howto_lines):
            text_entity.enabled = i < len(lines)
            text_entity.text = lines[i] if i < len(lines) else ""

    def show_report(self, lines: list[str]) -> None:
        self.back_target = "pause"
        self.screen = "report"
        self._report_lines = list(lines)
        self.cursor = 0
        self._show_shell()
        self.title.text = "YEAR REPORT"
        self.subtitle.text = "the farm books"
        self.title.enabled = self.subtitle.enabled = True
        self.howto_title.enabled = False
        for i, text_entity in enumerate(self.howto_lines):
            text_entity.enabled = i < len(lines)
            text_entity.text = lines[i] if i < len(lines) else ""

    def hide(self) -> None:
        self._hide_all()

    # -- rendering ---------------------------------------------------------------
    def _render_items(self, items: tuple) -> None:
        for i, text_entity in enumerate(self.items):
            enabled = i < len(items)
            text_entity.enabled = enabled
            if not enabled:
                continue
            label = items[i]
            if self.screen == "main" and label == "CONTINUE" and not self.continue_available:
                label += "   (no save)"
                text_entity.color = color.rgba(0.45, 0.5, 0.58, 0.9)
            else:
                text_entity.color = color.white
            if i == self.cursor:
                text_entity.text = f">  {label}  <"
                text_entity.color = color.rgb(0.5, 0.95, 1.0)
            else:
                text_entity.text = f"   {label}"

    def _setting_value_label(self, key: str, kind: str) -> str:
        value = self.settings.get(key, DEFAULT_SETTINGS.get(key))
        if kind == "toggle_mute":
            return "muted" if self.settings.get("muted") else "on"
        if kind == "toggle":
            return "on" if value else "off"
        if key == "difficulty":
            return DIFFICULTY_MODES.get(value, {}).get("label", str(value))
        if key == "victory":
            return VICTORY_MODES.get(value, {}).get("label", str(value))
        if key == "master_volume":
            return f"{int(float(value) * 100)}%"
        if key == "ui_scale":
            return f"{float(value):.2f}x"
        if key == "fov":
            return f"{int(value)} deg"
        return str(value)

    def _render_settings(self) -> None:
        for i, text_entity in enumerate(self.settings_lines):
            if i >= len(self.SETTINGS_ROWS):
                text_entity.enabled = False
                continue
            key, label, kind, _order = self.SETTINGS_ROWS[i]
            text_entity.enabled = True
            shown = self._setting_value_label(key, kind)
            text_entity.text = f"{label:<22}< {shown} >"
            text_entity.color = color.rgb(0.5, 0.95, 1.0) if i == self.cursor else color.white

    # -- input --------------------------------------------------------------------
    def handle(self, key: str) -> str | None:
        """Translate a raw key into an action token; None if unhandled."""
        if self.screen == "report" and key in ("escape", "enter"):
            self.show_pause()
            return "back"
        if key in ("w", "up arrow", "up"):
            count = max(1, self._item_count())
            self.cursor = (self.cursor - 1) % count
            self._refresh()
            return None
        if key in ("s", "down arrow", "down"):
            count = max(1, self._item_count())
            self.cursor = (self.cursor + 1) % count
            self._refresh()
            return None
        if key in ("a", "left arrow") and self.screen == "settings":
            self._cycle_setting_at(self.cursor, forward=False)
            return None
        if key in ("d", "right arrow") and self.screen == "settings":
            self._cycle_setting_at(self.cursor, forward=True)
            return None
        if key == "enter":
            return self._select()
        if key == "escape":
            if self.screen in ("settings", "howto", "report"):
                target = getattr(self, "back_target", "main")
                self.cursor = 0
                if target == "pause":
                    self.show_pause()
                else:
                    self.show_main()
                return "back"
            if self.screen == "pause":
                return "resume"
            return "quit"
        if self.screen == "howto" and key in ("a", "d", "left arrow", "right arrow"):
            self.howto_page = (self.howto_page + (1 if key in ("d", "right arrow") else -1)) % len(self.HOWTO_PAGES)
            self.show_howto(self.howto_page)
            return None
        return None

    def _item_count(self) -> int:
        if self.screen == "settings":
            return len(self.SETTINGS_ROWS)
        if self.screen == "pause":
            return len(self.PAUSE_ITEMS)
        if self.screen in ("howto", "report"):
            return 1
        return len(self.MAIN_ITEMS)

    def _refresh(self) -> None:
        if self.screen == "main":
            self._render_items(self.MAIN_ITEMS)
        elif self.screen == "pause":
            self._render_items(self.PAUSE_ITEMS)
        elif self.screen == "settings":
            self._render_settings()

    def _cycle_setting_at(self, index: int, forward: bool = True) -> None:
        if index < 0 or index >= len(self.SETTINGS_ROWS):
            return
        key, _label, kind, order = self.SETTINGS_ROWS[index]
        step = 1 if forward else -1
        if kind in ("toggle", "toggle_mute"):
            # muted is stored as muted bool; toggle_mute flips muted
            if kind == "toggle_mute":
                self.settings["muted"] = not bool(self.settings.get("muted", False))
            else:
                self.settings[key] = not bool(self.settings.get(key, False))
        elif kind in ("cycle_list", "cycle_num") and order:
            current = self.settings.get(key, order[0])
            try:
                # numeric lists may be ints/floats; tolerate type noise
                if current not in order:
                    # find closest for floats
                    if kind == "cycle_num":
                        current = min(order, key=lambda v: abs(float(v) - float(current)))
                    else:
                        current = order[0]
                idx = list(order).index(current)
            except Exception:
                idx = 0
            self.settings[key] = order[(idx + step) % len(order)]
        self._render_settings()
        if self.on_settings_changed is not None:
            self.on_settings_changed(dict(self.settings))

    def _cycle_setting(self, key: str, forward: bool = True) -> None:
        """Back-compat helper used by older tests."""
        for i, row in enumerate(self.SETTINGS_ROWS):
            if row[0] == key:
                self._cycle_setting_at(i, forward=forward)
                return
        if key == "quality":
            index = QUALITY_ORDER.index(self.settings.get("quality", "medium"))
            self.settings["quality"] = QUALITY_ORDER[(index + (1 if forward else -1)) % len(QUALITY_ORDER)]
        elif key in ("muted", "glide"):
            self.settings[key] = not self.settings.get(key, False)
        self._render_settings()
        if self.on_settings_changed is not None:
            self.on_settings_changed(dict(self.settings))

    def _select(self) -> str | None:
        if self.screen == "settings":
            self._cycle_setting_at(self.cursor, forward=True)
            return None
        if self.screen == "howto":
            self.howto_page = (self.howto_page + 1) % len(self.HOWTO_PAGES)
            self.show_howto(self.howto_page)
            return None
        if self.screen == "report":
            self.show_pause()
            return "back"
        if self.screen == "pause":
            action = ("resume", "save", "report", "settings", "quit_to_title")[self.cursor]
            if action == "settings":
                self.show_settings(dict(self.settings))
            self.cursor = 0
            return action
        # Main menu. Token stays new_game so the shell action map does not break.
        action = ("new_game", "continue", "load", "settings", "howto", "quit")[self.cursor]
        if action == "continue" and not self.continue_available:
            return None
        if action == "settings":
            self.show_settings(dict(self.settings))
        elif action == "howto":
            self.show_howto(0)
        self.cursor = 0
        return action
