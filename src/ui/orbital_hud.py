"""HUD for the orbital supply-chain layer.

Drawn with Ursina's UI primitives so it inherits the existing
``game/ui/hud.py`` styling conventions rather than pulling in a second UI
toolkit.
"""

from __future__ import annotations

from ursina import Entity, Text, Vec3, camera, color

from ..config import SHIP_CARGO_CAPACITY, SIM_SECONDS_PER_DAY
from ..simulation.bodies import BODIES


class OrbitalHUD:
    """Left panel: mission clock, fleet and the active transfer plan."""

    def __init__(self, targets: tuple[str, ...]):
        self.targets = targets
        self.target_index = 0

        panel = Entity(parent=camera.ui, model="quad",
                       color=color.rgba(0.045, 0.06, 0.10, 0.90),
                       scale=(0.31, 0.94), position=(-0.615, 0.0, 0.0))
        self.panel = panel

        self.title = Text(text="ORBITAL LOGISTICS", parent=camera.ui, position=(-0.755, 0.42, -0.1),
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
            text="[ / ] warp   TAB target   ENTER dispatch   S sell ore   X drill   M repair   1-4 buy ship   F5/F9 save/load",
            parent=camera.ui, scale=0.46,
            color=color.rgba(0.7, 0.8, 0.9, 0.8), origin=(-0.5, 0), position=(-0.755, -0.47, -0.1),
        )
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
            Text(text="", parent=camera.ui, position=(0.485, 0.30 - i * 0.026, -0.1),
                 scale=0.62, origin=(-0.5, 0))
            for i in range(7)
        ]
        self.ops_title = Text(text="FLEET OPS", parent=camera.ui, position=(0.485, 0.085, -0.1),
                              scale=0.72, color=color.yellow, origin=(-0.5, 0))
        self.ops_lines = [
            Text(text="", parent=camera.ui, position=(0.485, 0.055 - i * 0.026, -0.1),
                 scale=0.62, origin=(-0.5, 0))
            for i in range(7)
        ]
        self.tutorial = Text(text="", parent=camera.ui, position=(0.0, -0.42, -0.1),
                             scale=0.55, color=color.rgba(0.55, 0.9, 1.0, 0.95),
                             origin=(0.0, 0))
        self.ticker = Text(text="", parent=camera.ui, position=(0.0, -0.51, -0.1),
                           scale=0.5, color=color.rgba(0.75, 0.85, 0.95, 0.9),
                           origin=(0.0, 0))

    # -- helpers -------------------------------------------------------------
    def selected_target(self) -> str:
        return self.targets[self.target_index]

    def cycle_target(self, direction: int = 1) -> str:
        self.target_index = (self.target_index + direction) % len(self.targets)
        return self.selected_target()

    # -- refresh -------------------------------------------------------------
    def update(self, sim, colony_state: dict | None = None, message: str = "",
               extra: dict | None = None) -> None:
        days = sim.time / SIM_SECONDS_PER_DAY
        self.clock.text = f"Mission day {days:,.0f}   (year {days / 365.25:.2f})"
        self.warp.text = f"Time warp: {sim.warp_days_per_second:.0f} sim-days / real-second"

        if extra is not None:
            self._update_ops_panel(extra)
        else:
            self._clear_ops_panel()

        target_key = self.selected_target()
        target_name = BODIES[target_key].name
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
                    ("Target", f"{target_name}  (a={BODIES[target_key].elements.a:.2f} AU)"),
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
                    ("Target", f"{target_name}  (a={BODIES[target_key].elements.a:.2f} AU)"),
                    ("Window opens in", f"{wait_days:,.0f} d"),
                    ("Time of flight", f"{window.tof / SIM_SECONDS_PER_DAY:,.0f} d"),
                    ("Departure burn", f"{sim.delta_v_km_s(window.dv_depart) * 1000.0:,.0f} m/s"),
                    ("Arrival match", f"{sim.delta_v_km_s(window.dv_arrive) * 1000.0:,.0f} m/s"),
                    ("Round-trip cost", f"{sim.delta_v_km_s(window.total_delta_v) * 1000.0 * 2:,.0f} m/s (est.)"),
                    ("Cargo", f"{SHIP_CARGO_CAPACITY:.0f} t of iron / components / water / ice"),
                ]
            for line, (label, value) in zip(self.plan_lines, rows):
                line.text = f"{label:<17}{value}"

        for line in self.fleet_lines:
            line.text = ""
        for line, report in zip(self.fleet_lines, sim.fleet_report()):
            eta = f"  ETA {report['eta_days']:,.0f}d" if report["status"] in ("outbound", "inbound", "pending") else ""
            hull = f"  H{report['hull']:3.0f}%" if "hull" in report else ""
            line.text = (
                f"{report['name']:<8}{report['status']:<9}{report['at']:<20}"
                f"{report['delta_v_left']:>6,.0f} m/s{eta}{hull}"
            )
            line.color = (
                color.orange if report["status"] in ("outbound", "inbound")
                else color.red if report["delta_v_left"] < 2000.0
                else color.white
            )
            if "hull" in report and report["hull"] < 40.0:
                line.color = color.red

        for line in self.log_lines:
            line.text = ""
        recent = sim.log[-len(self.log_lines):]
        for line, entry in zip(self.log_lines, recent):
            line.text = f"d{entry.time / SIM_SECONDS_PER_DAY:>6,.0f}  {entry.text}"

        if colony_state is not None:
            delivered = sim.stats["mass_delivered"]
            self.help.text = (
                f"[ / ] warp   TAB target   ENTER dispatch   S sell   X drill   M repair   1-4 buy   F5/F9 save"
                f"      |      colony storage used {colony_state.get('used', 0):,.0f} / "
                f"{colony_state.get('capacity', 0):,.0f}    lifetime delivered {delivered:,.0f} t"
            )
        self.status.text = message

    # -- market / ops panel ---------------------------------------------------
    def _update_ops_panel(self, extra: dict) -> None:
        self.credits.text = f"Treasury  {extra.get('credits', 0.0):,.0f} cr"
        self.spark.text = extra.get("credits_spark", "")[:46]
        for line, (res, price, trend) in zip(self.price_lines, extra.get("prices", [])):
            line.text = f"{res:<11}{price:>7,.1f} cr/t  {trend}"
            line.color = (
                color.yellow if trend == "^"
                else color.orange if trend == "v"
                else color.white
            )
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

        summary = "  ".join(filter(None, (extra.get("rep_line", ""), extra.get("life_line", ""))))
        lines[6].text = summary
        if "ALERT" in summary:
            lines[6].color = color.red
        elif "LOW" in summary:
            lines[6].color = color.orange
        else:
            lines[6].color = color.white
        self.tutorial.text = extra.get("tutorial", "")

    def _clear_ops_panel(self) -> None:
        self.credits.text = ""
        self.spark.text = ""
        for line in self.price_lines:
            line.text = ""
        for line in self.ops_lines:
            line.text = ""
        self.tutorial.text = ""
        self.ticker.text = ""
