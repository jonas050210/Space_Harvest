"""HUD for the orbital supply-chain layer.

Drawn with Ursina's UI primitives so it inherits the existing
``game/ui/hud.py`` styling conventions rather than pulling in a second UI
toolkit.
"""

from __future__ import annotations

import math

from ursina import Button, Entity, Text, camera, color

from src.app.controls import COMMAND_BAR, help_line

from ..config import (
    SHIP_CARGO_CAPACITY,
    SIM_SECONDS_PER_DAY,
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


# Backward compat - MenuOverlay moved to src.ui.menu
try:
    from src.ui.menu import MenuOverlay  # noqa: F401
except Exception:
    pass
