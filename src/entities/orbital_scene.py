"""Builds and updates the 3-D view of the trade network.

This is the only place that converts simulation units (AU) into scene units,
so the physics never sees the render scale.

The look is deliberately stylised rather than realistic: an inverted starfield
dome, a sun with a layered billboard glow, unlit textured planets with
billboard name tags, a scattered asteroid belt for depth, and soft unlit
colour throughout so everything stays readable at game zoom.
"""

from __future__ import annotations

import math
import os
import random

from ursina import Entity, Mesh, Texture, Vec3, color

from ..config import SCENE_UNITS_PER_AU
from ..simulation.bodies import BODIES, orbit_points
from .ship import Freighter, OrbitLine

_TEX_ROOT = os.path.join("assets", "textures", "game")


def _tex(name: str) -> str | None:
    """Texture path relative to the process CWD, if the file exists."""
    path = os.path.join(_TEX_ROOT, name)
    return path if os.path.isfile(path) else None


def au_to_scene(point) -> Vec3:
    """Convert a heliocentric AU position into scene coordinates."""
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return Vec3(x, z, -y) * SCENE_UNITS_PER_AU


class OrbitalScene:
    """Owns the sky, the sun, the bodies, their orbit rings and the fleet."""

    def __init__(self, parent=None):
        self.parent = parent
        self.body_entities: dict[str, Entity] = {}
        self.orbit_lines: dict[str, OrbitLine] = {}
        self.ships: dict[str, Freighter] = {}
        self.labels: dict[str, Entity] = {}
        self.orbits_visible = True
        self._asteroid_scatter: list[Entity] = []
        self.build()

    # -- construction --------------------------------------------------------
    def build(self) -> None:
        self._build_sky()
        self._build_sun()
        for key, body in BODIES.items():
            if key == "nix":  # Aurelia's moon is drawn relative to its primary
                continue
            self._build_body(key, body)
        self._build_asteroid_belt()

    def _build_sky(self) -> None:
        """An inverted textured dome so the whole sky is a starfield."""
        stars = _tex("skybox_stars.png")
        if stars is not None:
            dome = Entity(parent=self.parent, model="sphere",
                          scale=420.0, double_sided=True, unlit=True)
            dome.texture = stars
            dome.cull_face = "front"  # render the inside
            dome.rotation_x = 180.0   # keep the seam behind the camera start
            self.sky_dome = dome
        else:
            self.sky_dome = None

    def _build_sun(self) -> None:
        """Emissive core plus two billboard glow layers for a soft corona."""
        self.sun = Entity(parent=self.parent, model="sphere", scale=2.4,
                          color=color.rgb(1.0, 0.93, 0.62), unlit=True)
        self.sun_glow: list[Entity] = []
        for size, opacity in ((9.0, 0.55), (18.0, 0.28)):
            glow = Entity(parent=self.parent, model="quad", scale=size,
                          color=color.rgba(1.0, 0.82, 0.45, opacity),
                          billboard=True, unlit=True)
            glow_texture = _tex("sun_glow.png")
            if glow_texture is not None:
                glow.texture = glow_texture
            self.sun_glow.append(glow)

    def _build_body(self, key: str, body) -> None:
        rgb = body.palette
        entity = Entity(
            parent=self.parent,
            model="sphere",
            scale=0.32 + 0.30 * body.render_scale,
            color=color.rgb(*rgb),
            unlit=True,
        )
        texture = _tex(f"{key}.png")
        if texture is not None:
            entity.texture = texture
        if key == "gas_giant_orbit":
            # Ring plane: two flat circles, faintly tinted.
            for ring_scale, ring_opacity in ((3.4, 0.30), (4.3, 0.18)):
                ring = Entity(parent=entity, model="circle", scale=ring_scale,
                              color=color.rgba(0.88, 0.76, 0.96, ring_opacity),
                              rotation_x=78, unlit=True, double_sided=True)
        self.body_entities[key] = entity

        pts = orbit_points(key, samples=192)
        scene_pts = [au_to_scene(p) for p in pts]
        line_color = color.rgba(min(1.0, rgb[0] * 1.1), min(1.0, rgb[1] * 1.1),
                                min(1.0, rgb[2] * 1.1), 0.42)
        self.orbit_lines[key] = OrbitLine(scene_pts, line_color, parent=self.parent)

        # Billboard name tag floating above the body.
        tag = _tex(f"label_{key}.png")
        if tag is not None:
            label = Entity(parent=entity, model="quad",
                           scale=(2.3, 0.41), position=(0, 1.35, 0),
                           texture=tag, billboard=True, unlit=True)
            self.labels[key] = label

    def _build_asteroid_belt(self) -> None:
        """A few hundred cheap rocks between the belt bodies, for depth."""
        if len(self._asteroid_scatter) > 0:
            return
        rng = random.Random(11)
        texture = _tex("metallic_belt.png")
        for _ in range(240):
            a = rng.uniform(1.35, 2.25)
            angle = rng.uniform(0.0, 2.0 * math.pi)
            drift = rng.uniform(-0.05, 0.05)
            x = a * math.cos(angle)
            y = a * math.sin(angle)
            z = drift
            rock = Entity(parent=self.parent, model="sphere",
                          scale=rng.uniform(0.05, 0.22),
                          rotation=(rng.uniform(0, 360), rng.uniform(0, 360), 0),
                          color=color.rgb(0.45, 0.45, 0.52), unlit=True)
            if texture is not None and rng.random() < 0.3:
                rock.texture = texture
            rock.position = Vec3(x, z, -y) * SCENE_UNITS_PER_AU
            self._asteroid_scatter.append(rock)

    def make_ship(self, name: str, class_key: str | None = None) -> Freighter:
        ship = Freighter(name, parent=self.parent)
        if class_key is not None:
            ship.apply_class_tint(class_key)
        self.ships[name] = ship
        return ship

    def set_orbits_visible(self, visible: bool) -> None:
        self.orbits_visible = visible
        for line in self.orbit_lines.values():
            line.enabled = visible

    # -- per-frame -----------------------------------------------------------
    def update(self, sim) -> None:
        """Sync every mesh with the simulation clock."""
        from ..config import MU_SUN
        from ..maths import windows as window_solver

        for key, entity in self.body_entities.items():
            body = sim.bodies.get(key, BODIES[key])
            r, _ = window_solver.body_state(body.elements, MU_SUN, sim.time)
            entity.position = au_to_scene(r)
            entity.rotation_y += 0.15
        for rock in self._asteroid_scatter:
            rock.rotation_y += 0.35
            rock.rotation_x += 0.12

        for report in sim.fleet_report():
            ship_mesh = self.ships.get(report["name"])
            if ship_mesh is None:
                ship_mesh = self.make_ship(report["name"], report.get("class"))
            sim_ship = next(s for s in sim.ships if s.name == report["name"])
            r, v = sim_ship.state_at(sim.time)
            ship_mesh.follow(au_to_scene(r), Vec3(float(v[0]), float(v[2]), -float(v[1])))
            ship_mesh.set_loaded(report["cargo"] > 0.0,
                                 report["cargo"] / max(1.0, sim_ship.capacity))
            ship_mesh.set_thrusting(report["status"] in ("pending", "outbound", "inbound"))
