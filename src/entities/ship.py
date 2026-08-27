"""Visual representation of a colony freighter.

Kept deliberately cheap: a small hull, a cargo pod that appears when loaded
and a fading trail, all from Ursina primitives, so a few dozen ships stay
well inside an 8 GB card.
"""

from __future__ import annotations

from ursina import Entity, Mesh, Vec3, color, destroy

TRAIL_LENGTH = 90


class Freighter(Entity):
    """A ship mesh that trails the arc it is flying."""

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ship_name = name
        self.hull = Entity(parent=self, model="cube", scale=Vec3(0.22, 0.22, 0.62), color=color.white)
        self.pod = Entity(parent=self, model="sphere", scale=0.2, position=(0, 0, 0.42), color=color.yellow, enabled=False)
        self.engine_glow = Entity(parent=self, model="sphere", scale=0.16, position=(0, 0, -0.38), color=color.cyan)
        self._trail: list[Entity] = []
        self._since_trail = 0.0

    def set_loaded(self, loaded: bool, fraction: float = 1.0) -> None:
        """Show or hide the cargo pod, sized by how full the hold is."""
        self.pod.enabled = loaded and fraction > 0.0
        self.pod.scale = 0.1 + 0.22 * max(0.0, min(1.0, fraction))

    def set_thrusting(self, thrusting: bool) -> None:
        self.engine_glow.enabled = thrusting
        self.engine_glow.scale = 0.26 if thrusting else 0.16

    def follow(self, world_position: Vec3, heading: Vec3 | None = None) -> None:
        """Move the hull and extend the trail."""
        self.position = world_position
        if heading is not None and heading.length() > 1e-6:
            self.look_at(self.position + heading)
        self._since_trail += 1.0
        if self._since_trail >= 1.0:
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
