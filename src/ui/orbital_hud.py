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
            text="[ / ] warp    TAB next target    ENTER dispatch    O orbits    F follow    C colony cam",
            parent=camera.ui, scale=0.46,
            color=color.rgba(0.7, 0.8, 0.9, 0.8), origin=(-0.5, 0), position=(-0.755, -0.47, -0.1),
        )
        self.status = Text(text="", parent=camera.ui, position=(-0.29, -0.47, -0.1),
                           scale=0.5, color=color.orange, origin=(0.5, 0))

    # -- helpers -------------------------------------------------------------
    def selected_target(self) -> str:
        return self.targets[self.target_index]

    def cycle_target(self, direction: int = 1) -> str:
        self.target_index = (self.target_index + direction) % len(self.targets)
        return self.selected_target()

    # -- refresh -------------------------------------------------------------
    def update(self, sim, colony_state: dict | None = None, message: str = "") -> None:
        days = sim.time / SIM_SECONDS_PER_DAY
        self.clock.text = f"Mission day {days:,.0f}   (year {days / 365.25:.2f})"
        self.warp.text = f"Time warp: {sim.warp_days_per_second:.0f} sim-days / real-second"

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
            line.text = (
                f"{report['name']:<7}{report['status']:<9}{report['at']:<21}"
                f"{report['delta_v_left']:>6,.0f} m/s{eta}"
            )
            line.color = (
                color.orange if report["status"] in ("outbound", "inbound")
                else color.red if report["delta_v_left"] < 2000.0
                else color.white
            )

        for line in self.log_lines:
            line.text = ""
        recent = sim.log[-len(self.log_lines):]
        for line, entry in zip(self.log_lines, recent):
            line.text = f"d{entry.time / SIM_SECONDS_PER_DAY:>6,.0f}  {entry.text}"

        if colony_state is not None:
            delivered = sim.stats["mass_delivered"]
            self.help.text = (
                f"[ / ] warp    TAB next target    ENTER dispatch    O orbits    F follow    C colony cam"
                f"      |      colony storage used {colony_state.get('used', 0):,.0f} / "
                f"{colony_state.get('capacity', 0):,.0f}    lifetime delivered {delivered:,.0f} t"
            )
        self.status.text = message
