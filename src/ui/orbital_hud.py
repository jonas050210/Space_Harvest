"""HUD for the orbital supply-chain layer.

Drawn with Ursina's UI primitives so it inherits the existing
``game/ui/hud.py`` styling conventions rather than pulling in a second UI
toolkit.
"""

from __future__ import annotations

import math

from ursina import Button, Entity, Text, camera, color

from src.app.controls import COMMAND_BAR, HOWTO_PAGES as CONTROL_HOWTO_PAGES, help_line

from ..config import (
    DEFAULT_SETTINGS,
    DIFFICULTY_MODES,
    DIFFICULTY_ORDER,
    FOV_ORDER,
    MASTER_VOLUME_STEPS,
    QUALITY_ORDER,
    RESOLUTION_ORDER,
    SHIP_CARGO_CAPACITY,
    SIM_SECONDS_PER_DAY,
    UI_SCALE_ORDER,
    VICTORY_MODES,
    VICTORY_ORDER,
    VIEW_MODES,
)
from ..simulation.bodies import BODIES


class OrbitalHUD:
    """Left panel: mission clock, fleet and the active transfer plan."""

    def __init__(self, targets: tuple[str, ...], on_command=None):
        self.targets = targets
        self.target_index = 0
        self.on_command = on_command
        self.command_buttons: list = []

        panel = Entity(parent=camera.ui, model="quad",
                       color=color.rgba(0.045, 0.06, 0.10, 0.90),
                       scale=(0.31, 0.94), position=(-0.615, 0.0, 0.0))
        self.panel = panel

        self.title = Text(text="SPACE HARVEST", parent=camera.ui, position=(-0.755, 0.42, -0.1),
                          scale=0.9, color=color.cyan, origin=(-0.5, 0))
        self.clock = Text(text="", parent=camera.ui, position=(-0.755, 0.375, -0.1),
                          scale=0.75, origin=(-0.5, 0))
        self.warp = Text(text="", parent=camera.ui, position=(-0.755, 0.345, -0.1),
                         scale=0.62, color=color.light_gray, origin=(-0.5, 0))

        self.plan_header = Text(text="TRANSFER PLAN", parent=camera.ui, position=(-0.755, 0.285, -0.1),
                                scale=0.72, color=color.yellow, origin=(-0.5, 0))
        self.plan_lines = [
            Text(text="", parent=camera.ui, position=(-0.755, 0.255 - i * 0.028, -0.1),
                 scale=0.62, origin=(-0.5, 0))
            for i in range(7)
        ]

        self.fleet_header = Text(text="FLEET", parent=camera.ui, position=(-0.755, 0.045, -0.1),
                                 scale=0.72, color=color.yellow, origin=(-0.5, 0))
        self.fleet_lines = [
            Text(text="", parent=camera.ui, position=(-0.755, 0.015 - i * 0.026, -0.1),
                 scale=0.58, origin=(-0.5, 0))
            for i in range(10)
        ]

        self.log_header = Text(text="FLIGHT LOG", parent=camera.ui, position=(-0.755, -0.245, -0.1),
                               scale=0.72, color=color.yellow, origin=(-0.5, 0))
        self.log_lines = [
            Text(text="", parent=camera.ui, position=(-0.755, -0.275 - i * 0.026, -0.1),
                 scale=0.52, color=color.light_gray, origin=(-0.5, 0))
            for i in range(6)
        ]

        self.help = Text(
            text=help_line(),
            parent=camera.ui, scale=0.42,
            color=color.rgba(0.7, 0.8, 0.9, 0.8), origin=(-0.5, 0), position=(-0.755, -0.47, -0.1),
        )
        self._build_command_bar()
        self.status = Text(text="", parent=camera.ui, position=(-0.29, -0.47, -0.1),
                           scale=0.5, color=color.orange, origin=(0.5, 0))

        # Right panel: Earth market, treasury and fleet operations.
        ops_panel = Entity(parent=camera.ui, model="quad",
                           color=color.rgba(0.045, 0.06, 0.10, 0.90),
                           scale=(0.30, 0.94), position=(0.62, 0.0, 0.0))
        self.ops_panel = ops_panel
        self.market_title = Text(text="EARTH MARKET", parent=camera.ui, position=(0.485, 0.42, -0.1),
                                 scale=0.9, color=color.cyan, origin=(-0.5, 0))
        self.credits = Text(text="", parent=camera.ui, position=(0.485, 0.375, -0.1),
                            scale=0.8, color=color.yellow, origin=(-0.5, 0))
        self.spark = Text(text="", parent=camera.ui, position=(0.485, 0.345, -0.1),
                          scale=0.62, color=color.gray, origin=(-0.5, 0))
        self.price_lines = [
            Text(text="", parent=camera.ui, position=(0.485, 0.30 - i * 0.022, -0.1),
                 scale=0.55, origin=(-0.5, 0))
            for i in range(10)
        ]
        self.ops_title = Text(text="FLEET OPS", parent=camera.ui, position=(0.485, 0.085, -0.1),
                              scale=0.72, color=color.yellow, origin=(-0.5, 0))
        self.ops_lines = [
            Text(text="", parent=camera.ui, position=(0.485, 0.055 - i * 0.026, -0.1),
                 scale=0.62, origin=(-0.5, 0))
            for i in range(8)
        ]
        self.tutorial = Text(text="", parent=camera.ui, position=(0.0, -0.42, -0.1),
                             scale=0.55, color=color.rgba(0.55, 0.9, 1.0, 0.95),
                             origin=(0.0, 0))
        self.board_header = Text(text="NEXT WINDOWS", parent=camera.ui, position=(0.485, -0.165, -0.1),
                                 scale=0.62, color=color.yellow, origin=(-0.5, 0))
        self.board_lines = [
            Text(text="", parent=camera.ui, position=(0.485, -0.195 - i * 0.024, -0.1),
                 scale=0.58, origin=(-0.5, 0))
            for i in range(6)
        ]
        # Body dossier card (selected target) -- bottom-centre under the banner.
        self.dossier_lines = [
            Text(text="", parent=camera.ui, position=(0.0, 0.22 - i * 0.028, -0.15),
                 scale=0.55, origin=(0.0, 0),
                 color=color.rgba(0.85, 0.92, 1.0, 0.92))
            for i in range(5)
        ]
        self.ticker = Text(text="", parent=camera.ui, position=(0.0, -0.51, -0.1),
                           scale=0.5, color=color.rgba(0.75, 0.85, 0.95, 0.9),
                           origin=(0.0, 0))
        # Toast stack: the newest few messages, top-centre.
        self.toast_lines = [
            Text(text="", parent=camera.ui, position=(0.0, 0.46 - i * 0.035, -0.1),
                 scale=0.62, origin=(0.0, 0),
                 color=color.rgba(0.95, 0.97, 1.0, 0.95))
            for i in range(3)
        ]
        # Launch-window banner: big, blinking, unmissable.
        self.launch_banner = Text(text="", parent=camera.ui, position=(0.0, 0.30, -0.2),
                                  scale=1.35, origin=(0.0, 0), color=color.rgb(0.45, 1.0, 0.55))
        self._blink = 0

    # -- helpers -------------------------------------------------------------
    def selected_target(self) -> str:
        return self.targets[self.target_index]

    def cycle_target(self, direction: int = 1) -> str:
        self.target_index = (self.target_index + direction) % len(self.targets)
        return self.selected_target()

    def set_target(self, key: str) -> bool:
        """Select ``key`` directly (click-picking); False if unknown."""
        if key in self.targets:
            self.target_index = self.targets.index(key)
            return True
        return False

    def _build_command_bar(self) -> None:
        """Mouse-first actions along the bottom. Hidden on title / pause."""
        if self.on_command is None:
            return
        n = len(COMMAND_BAR)
        for i, (label, action) in enumerate(COMMAND_BAR):
            x = -0.36 + i * (0.72 / max(1, n - 1))
            button = Button(
                text=label,
                parent=camera.ui,
                scale=(0.105, 0.042),
                position=(x, -0.385, -0.2),
                color=color.rgba(0.07, 0.14, 0.22, 0.92),
                highlight_color=color.rgb(0.18, 0.42, 0.52),
                pressed_color=color.rgb(0.25, 0.55, 0.45),
                on_click=lambda a=action: self.on_command(a),
            )
            try:
                button.text_entity.scale = 0.6
            except Exception:
                pass
            self.command_buttons.append(button)

    def set_commands_visible(self, visible: bool) -> None:
        for button in self.command_buttons:
            button.enabled = bool(visible)

    def apply_style(self, contrast: bool = True) -> None:
        """High-contrast panels for the accessibility toggle."""
        if contrast:
            fill = color.rgba(0.02, 0.03, 0.06, 0.94)
        else:
            fill = color.rgba(0.045, 0.06, 0.10, 0.82)
        self.panel.color = fill
        self.ops_panel.color = fill

    # -- refresh -------------------------------------------------------------
    def update(self, sim, colony_state: dict | None = None, message: str = "",
               extra: dict | None = None) -> None:
        days = sim.time / SIM_SECONDS_PER_DAY
        self.clock.text = f"Mission day {days:,.0f}   (year {days / 365.25:.2f})"
        self.warp.text = f"Time warp: {sim.warp_days_per_second:.0f} sim-days / real-second"

        if extra is not None:
            self._update_ops_panel(extra)
            self._update_toasts(extra.get("toasts", []))
            self._update_banner(extra.get("window_line", ""), extra.get("window_open", False))
        else:
            self._clear_ops_panel()

        target_key = self.selected_target()
        body = getattr(sim, "bodies", BODIES).get(target_key) or BODIES.get(target_key)
        target_name = body.name if body is not None else target_key
        semi = body.elements.a if body is not None else 0.0
        window = sim.launch_window("colony", target_key)
        self.plan_header.text = f"TRANSFER PLAN -> {target_name.upper()}"
        if window is None:
            self.plan_lines[0].text = "No intercept window found."
            for line in self.plan_lines[1:]:
                line.text = ""
        else:
            wait_days = max(0.0, (window.departure_time - sim.time) / SIM_SECONDS_PER_DAY)
            if extra is not None:
                rows = [
                    ("Target", f"{target_name}  (a={semi:.2f} AU)"),
                    ("Window opens in", f"{wait_days:,.0f} d"),
                    ("Time of flight", f"{window.tof / SIM_SECONDS_PER_DAY:,.0f} d"),
                    ("Departure burn", f"{sim.delta_v_km_s(window.dv_depart) * 1000.0:,.0f} m/s"),
                    ("Arrival match", f"{sim.delta_v_km_s(window.dv_arrive) * 1000.0:,.0f} m/s"),
                    ("Assay", extra.get("assay", "")),
                    ("Veins drawn", f"{extra.get('mined_t', 0.0):,.0f} t mined, "
                                    f"{extra.get('incidents', 0)} incidents"),
                ]
            else:
                rows = [
                    ("Target", f"{target_name}  (a={semi:.2f} AU)"),
                    ("Window opens in", f"{wait_days:,.0f} d"),
                    ("Time of flight", f"{window.tof / SIM_SECONDS_PER_DAY:,.0f} d"),
                    ("Departure burn", f"{sim.delta_v_km_s(window.dv_depart) * 1000.0:,.0f} m/s"),
                    ("Arrival match", f"{sim.delta_v_km_s(window.dv_arrive) * 1000.0:,.0f} m/s"),
                    ("Round-trip cost", f"{sim.delta_v_km_s(window.total_delta_v) * 1000.0 * 2:,.0f} m/s (est.)"),
                    ("Cargo", f"{SHIP_CARGO_CAPACITY:.0f} t hold"),
                ]
            for line, (label, value) in zip(self.plan_lines, rows, strict=False):
                line.text = f"{label:<17}{value}"

        for line in self.fleet_lines:
            line.text = ""
        for line, report in zip(self.fleet_lines, sim.fleet_report(), strict=False):
            eta = f"  ETA {report['eta_days']:,.0f}d" if report["status"] in ("outbound", "inbound", "pending") else ""
            parts = report.get("parts") or {}
            tag = "".join(code * count for code, count in
                          (("T", parts.get("tank", 0)), ("D", parts.get("drill", 0)),
                           ("Q", parts.get("quarters", 0))))
            tag = f" [{tag}]" if tag else ""
            hull = f"  H{report['hull']:3.0f}%" if "hull" in report else ""
            bar = ""
            if "dv_max" in report:
                filled = int(round(5.0 * report["delta_v_left"] / max(1.0, report["dv_max"])))
                bar = " " + "#" * filled + "." * (5 - filled)
            line.text = (
                f"{report['name']:<8}{report['status']:<9}{report['at']:<18}"
                f"{report['delta_v_left']:>6,.0f}{bar}{eta}{hull}{tag}"
            )
            selected = extra.get("selected_ship") if extra else None
            line.color = (
                color.orange if report["status"] in ("outbound", "inbound")
                else color.red if report["delta_v_left"] < 2000.0
                else color.white
            )
            if "hull" in report and report["hull"] < 40.0:
                line.color = color.red
            if selected and report["name"] == selected:
                line.color = color.rgb(0.45, 1.0, 0.75)
                if not line.text.startswith(">"):
                    line.text = "> " + line.text

        for line in self.log_lines:
            line.text = ""
        recent = sim.log[-len(self.log_lines):]
        for line, entry in zip(self.log_lines, recent, strict=False):
            line.text = f"d{entry.time / SIM_SECONDS_PER_DAY:>6,.0f}  {entry.text}"

        if colony_state is not None:
            delivered = sim.stats["mass_delivered"]
            self.help.text = (
                f"{help_line()}"
                f"      |      storage {colony_state.get('used', 0):,.0f}/"
                f"{colony_state.get('capacity', 0):,.0f}    hauled {delivered:,.0f} t"
            )
        self.status.text = message

    # -- toasts and the launch banner -----------------------------------------
    def _update_toasts(self, toasts: list[str]) -> None:
        for line, text in zip(self.toast_lines, toasts[-3:], strict=False):
            line.text = text
        for line in self.toast_lines[len(toasts[-3:]):]:
            line.text = ""

    def _update_banner(self, window_line: str, is_open: bool) -> None:
        self._blink += 1
        if is_open:
            # Blink roughly twice a second so the eye catches it.
            self.launch_banner.text = window_line if self._blink % 30 < 20 else ""
            self.launch_banner.color = color.rgb(0.45, 1.0, 0.55)
        else:
            self.launch_banner.text = window_line if window_line.startswith("Window in") else ""
            self.launch_banner.color = color.rgba(0.85, 0.9, 1.0, 0.8)

    # -- market / ops panel ---------------------------------------------------
    def _update_ops_panel(self, extra: dict) -> None:
        firsts_done, firsts_total = extra.get("firsts_count", (0, 0))
        self.credits.text = (f"Treasury  {extra.get('credits', 0.0):,.0f} cr"
                             f"   Firsts {firsts_done}/{firsts_total}")
        self.spark.text = extra.get("credits_spark", "")[:46]
        prices = list(extra.get("prices", []))
        focus = list(extra.get("price_focus") or [])
        by_res = {row[0]: row for row in prices}
        ordered = []
        for ore in focus:
            if ore in by_res:
                ordered.append(by_res.pop(ore))
        ordered.extend(sorted(by_res.values(), key=lambda row: -float(row[1])))
        for line, (res, price, trend) in zip(self.price_lines, ordered, strict=False):
            line.text = f"{res:<11}{price:>7,.1f} cr/t  {trend}"
            line.color = (
                color.yellow if trend == "^"
                else color.orange if trend == "v"
                else color.white
            )
        for line in self.price_lines[len(ordered):]:
            line.text = ""
        mode = extra.get("mode", "scrape")
        mode_label = "core drilling" if mode == "drill" else "surface scraping"
        lines = self.ops_lines
        lines[0].text = f"Mining: {mode_label}"
        lines[0].color = color.orange if mode == "drill" else color.white
        lines[1].text = f"Maintenance: {'auto' if extra.get('auto_repair') else 'OFF'}"
        lines[1].color = color.white if extra.get("auto_repair") else color.red
        hulls = extra.get("hull", {})
        worn = {name: pct for name, pct in hulls.items() if pct < 60.0}
        lines[2].text = (
            "Watch hull: " + ", ".join(f"{name} {pct:.0f}%" for name, pct in sorted(worn.items()))
            if worn else "All hulls sound"
        )
        lines[2].color = color.red if worn else color.white

        crew_line = extra.get("crew_line", "")
        lines[3].text = crew_line
        lines[3].color = color.orange if "tired" in crew_line else color.white

        weather = extra.get("weather", "")
        lines[4].text = weather or "Space weather: quiet"
        lines[4].color = color.red if weather.startswith("ALERT") else color.white

        lines[5].text = extra.get("contract_line", "")
        lines[5].color = color.yellow
        pending_line = extra.get("pending_line", "")
        if pending_line:
            lines[5].text = f"{lines[5].text}  |  {pending_line}"
            lines[5].color = color.orange

        board = extra.get("windows_board") or []
        for line, (name, days, is_open) in zip(self.board_lines, board, strict=False):
            if is_open:
                line.text = f"GO  {name}"
                line.color = color.rgb(0.45, 1.0, 0.55)
            elif math.isfinite(days):
                line.text = f"    {name:<20}{days:>6,.0f} d"
                line.color = color.white
            else:
                line.text = f"    {name:<20}  no window"
                line.color = color.rgba(0.6, 0.65, 0.75, 0.9)
        for line in self.board_lines[len(board):]:
            line.text = ""

        depot_line = extra.get("depot_line", "")
        parts_hint = extra.get("parts_hint", "")
        lines[7].text = "  ".join(filter(None, (depot_line, extra.get("depot_hint", ""),
                                                extra.get("station_hint", ""), parts_hint)))
        lines[7].color = color.cyan if "No depots" not in depot_line else color.white
        summary = "  ".join(filter(None, (extra.get("rep_line", ""), extra.get("life_line", ""))))
        route = extra.get("route_line", "")
        swarm = extra.get("swarm_line", "")
        view = extra.get("view_mode", "")
        survey = extra.get("survey_line", "")
        rival = extra.get("rival_line", "")
        extras = "  ".join(filter(None, (route, swarm, survey, rival, f"view:{view}" if view else "")))
        if extras:
            summary = f"{summary}  |  {extras}" if summary else extras
        lines[6].text = summary
        if "SWARM" in (swarm or ""):
            lines[6].color = color.rgb(0.45, 1.0, 0.75)
        if "ALERT" in summary:
            lines[6].color = color.red
        elif "LOW" in summary:
            lines[6].color = color.orange
        else:
            lines[6].color = color.white
        self.tutorial.text = extra.get("tutorial", "")
        dossier = extra.get("dossier") or []
        for line, text in zip(self.dossier_lines, dossier, strict=False):
            line.text = text[:72]
        for line in self.dossier_lines[len(dossier):]:
            line.text = ""
        # Pending dispatch confirm sits on the banner colour channel.
        if extra.get("pending_dispatch"):
            self.launch_banner.color = color.rgb(1.0, 0.85, 0.35)

    def _clear_ops_panel(self) -> None:
        self.credits.text = ""
        self.spark.text = ""
        for line in self.price_lines:
            line.text = ""
        for line in self.ops_lines:
            line.text = ""
        self.tutorial.text = ""
        self.ticker.text = ""
        self.launch_banner.text = ""
        for line in self.toast_lines:
            line.text = ""
        for line in self.dossier_lines:
            line.text = ""


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
