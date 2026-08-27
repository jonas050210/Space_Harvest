"""Visual representation of a colony freighter.

A stylised multi-part ship from Ursina primitives: nose cone, hull spine,
cargo pod, radiator fins and a billboard engine flare, plus a fading trail,
so a few dozen ships stay well inside an 8 GB card.
"""

from __future__ import annotations

import os

from ursina import Entity, Mesh, Vec3, color, destroy

TRAIL_LENGTH = 90
#: class-level trail switch (quality preset drives it)
TRAILS_ENABLED = True
_ENGINE_FLARE = os.path.join("assets", "textures", "game", "engine_glow.png")

#: hull accent tint per ship class, so the fleet reads at a glance
CLASS_TINTS = {
    "scout": (0.72, 0.90, 1.00),
    "freighter": (1.00, 1.00, 1.00),
    "refinery": (1.00, 0.92, 0.72),
    "hauler": (1.00, 0.85, 0.85),
}


class Freighter(Entity):
    """A ship mesh that trails the arc it is flying."""

    def __init__(self, name: str, *args, class_key: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ship_name = name
        # Per-class silhouettes: needle scout, blocky hauler, drummed refinery.
        hull_s, nose_s, nose_z = Vec3(0.20, 0.20, 0.52), Vec3(0.20, 0.20, 0.26), 0.34
        self.extra_parts: list[Entity] = []
        if class_key == "scout":
            hull_s, nose_s, nose_z = Vec3(0.11, 0.11, 0.66), Vec3(0.11, 0.11, 0.22), 0.44
        elif class_key == "hauler":
            hull_s = Vec3(0.30, 0.30, 0.40)
        elif class_key == "refinery":
            hull_s = Vec3(0.24, 0.24, 0.46)
        self.hull = Entity(parent=self, model="cube", scale=hull_s,
                           color=color.rgb(0.95, 0.97, 1.0))
        self.nose = Entity(parent=self, model="sphere", scale=nose_s,
                           position=(0, 0, nose_z), color=color.rgb(0.85, 0.90, 0.98))
        self.pod = Entity(parent=self, model="cube", scale=Vec3(0.26, 0.26, 0.30),
                          position=(0, 0, -0.05), color=color.rgb(1.0, 0.85, 0.45),
                          enabled=False)
        Entity(parent=self, model="cube", scale=Vec3(0.03, 0.26, 0.20),
               position=(0.13, 0, -0.12), color=color.rgb(0.75, 0.82, 0.92))
        Entity(parent=self, model="cube", scale=Vec3(0.03, 0.26, 0.20),
               position=(-0.13, 0, -0.12), color=color.rgb(0.75, 0.82, 0.92))
        if class_key == "scout":   # long comm mast
            self.extra_parts.append(Entity(
                parent=self, model="cube", scale=Vec3(0.02, 0.02, 0.5),
                position=(0, 0.16, -0.1), color=color.rgb(0.8, 0.9, 1.0)))
        if class_key == "hauler":  # second hull alongside: a barge
            self.extra_parts.append(Entity(
                parent=self, model="cube", scale=Vec3(0.16, 0.24, 0.36),
                position=(0.26, 0, 0.0), color=color.rgb(0.85, 0.88, 0.95)))
        if class_key == "refinery":  # processing drum
            self.extra_parts.append(Entity(
                parent=self, model="sphere", scale=Vec3(0.20, 0.20, 0.34),
                position=(0, 0.17, 0.05), color=color.rgb(0.9, 0.8, 0.6)))
        self.engine_glow = Entity(parent=self, model="quad", scale=0.30,
                                  position=(0, 0, -0.36), color=color.cyan,
                                  billboard=True, unlit=True)
        if os.path.isfile(_ENGINE_FLARE):
            self.engine_glow.texture = _ENGINE_FLARE
        self._trail: list[Entity] = []
        self._since_trail = 0.0

    def apply_class_tint(self, class_key: str) -> None:
        """Tint the hull spine by ship class."""
        rgb = CLASS_TINTS.get(class_key, (1.0, 1.0, 1.0))
        self.hull.color = color.rgb(*rgb)

    def set_loaded(self, loaded: bool, fraction: float = 1.0) -> None:
        """Show or hide the cargo pod, sized by how full the hold is."""
        self.pod.enabled = loaded and fraction > 0.0
        self.pod.scale = Vec3(0.26, 0.26, 0.16 + 0.30 * max(0.0, min(1.0, fraction)))

    def set_thrusting(self, thrusting: bool) -> None:
        self.engine_glow.enabled = thrusting
        self.engine_glow.scale = 0.42 if thrusting else 0.26

    def follow(self, world_position: Vec3, heading: Vec3 | None = None) -> None:
        """Move the hull and extend the trail."""
        self.position = world_position
        if heading is not None and heading.length() > 1e-6:
            self.look_at(self.position + heading)
        self._since_trail += 1.0
        if self._since_trail >= 1.0 and TRAILS_ENABLED:
            self._since_trail = 0.0
            dot = Entity(parent=self.parent, model="sphere", scale=0.055,
                         position=world_position, color=color.rgba(0.6, 0.85, 1.0, 0.55))
            dot.fade_out(duration=4.0)
            self._trail.append(dot)
            if len(self._trail) > TRAIL_LENGTH:
                # Ursina 8.x exposes destroy() as a module-level function.
                destroy(self._trail.pop(0))

    def clear_trail(self) -> None:
        for dot in self._trail:
            destroy(dot)
        self._trail.clear()


class OrbitLine(Entity):
    """A body's heliocentric orbit drawn as one connected line mesh.

    A single entity per orbit (160 segments would be 160 quads otherwise), so
    the scene stays cheap on the draw-call budget.
    """

    def __init__(self, points, body_color=color.white, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mesh = Mesh(
            vertices=[Vec3(p) for p in points],
            mode="line",
            thickness=1.5,
        )
        self.model = mesh
        self.color = color.rgba(body_color.r * 0.9, body_color.g * 0.9, body_color.b * 0.9, 0.55)
