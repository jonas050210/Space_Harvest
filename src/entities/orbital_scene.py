"""Builds and updates the 3-D view of the trade network.

This is the only place that converts simulation units (AU) into scene units,
so the physics never sees the render scale.
"""

from __future__ import annotations

import math

from ursina import Entity, Vec3, color

from ..config import SCENE_UNITS_PER_AU
from ..simulation.bodies import BODIES, orbit_points
from .ship import Freighter, OrbitLine


def au_to_scene(point) -> Vec3:
    """Convert a heliocentric AU position into scene coordinates."""
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return Vec3(x, z, -y) * SCENE_UNITS_PER_AU


class OrbitalScene:
    """Owns the sun, the bodies, their orbit rings and the freighter meshes."""

    def __init__(self, parent=None):
        self.parent = parent
        self.body_entities: dict[str, Entity] = {}
        self.orbit_lines: dict[str, OrbitLine] = {}
        self.ships: dict[str, Freighter] = {}
        self.labels: dict[str, Entity] = {}
        self.orbits_visible = True
        self.build()

    def build(self) -> None:
        # Sun: an emissive-looking sphere plus a soft halo.
        self.sun = Entity(parent=self.parent, model="sphere", scale=1.9, color=color.rgb(1.0, 0.92, 0.6))
        Entity(parent=self.sun, model="sphere", scale=1.5, color=color.rgba(1.0, 0.8, 0.35, 0.25))

        for key, body in BODIES.items():
            if key == "nix":  # Aurelia's moon is drawn relative to its primary
                continue
            rgb = body.palette
            entity = Entity(
                parent=self.parent, model="sphere",
                scale=0.32 + 0.30 * body.render_scale,
                color=color.rgb(rgb[0], rgb[1], rgb[2]),
            )
            if key == "gas_giant_orbit":
                ring = Entity(parent=entity, model="circle", scale=3.1,
                              color=color.rgba(0.85, 0.7, 0.95, 0.35), rotation_x=78)
                ring.double_sided = True
            self.body_entities[key] = entity

            pts = orbit_points(key, samples=160)
            scene_pts = [au_to_scene(p) for p in pts]
            self.orbit_lines[key] = OrbitLine(scene_pts, color.rgb(rgb[0], rgb[1], rgb[2]), parent=self.parent)

            label = Entity(parent=entity, model="quad", scale=(1.5, 0.32), position=(0, 1.5, 0),
                           color=color.rgba(rgb[0], rgb[1], rgb[2], 0.16), billboard=True)
            self.labels[key] = label

    def make_ship(self, name: str) -> Freighter:
        ship = Freighter(name, parent=self.parent)
        self.ships[name] = ship
        return ship

    def set_orbits_visible(self, visible: bool) -> None:
        self.orbits_visible = visible
        for line in self.orbit_lines.values():
            line.enabled = visible

    def update(self, sim) -> None:
        """Sync every mesh with the simulation clock."""
        from ..maths import windows as window_solver
        from ..config import MU_SUN

        for key, entity in self.body_entities.items():
            body = BODIES[key]
            r, _ = window_solver.body_state(body.elements, MU_SUN, sim.time)
            entity.position = au_to_scene(r)
            entity.rotation_y += 0.2

        for report in sim.fleet_report():
            ship_mesh = self.ships.get(report["name"])
            if ship_mesh is None:
                ship_mesh = self.make_ship(report["name"])
            sim_ship = next(s for s in sim.ships if s.name == report["name"])
            r, v = sim_ship.state_at(sim.time)
            ship_mesh.follow(au_to_scene(r), Vec3(float(v[0]), float(v[2]), -float(v[1])))
            ship_mesh.set_loaded(report["cargo"] > 0.0,
                                 report["cargo"] / max(1.0, sim_ship.capacity))
            ship_mesh.set_thrusting(report["status"] in ("pending", "outbound", "inbound"))
