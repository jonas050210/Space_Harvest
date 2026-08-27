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
import time

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
        self.belt_mesh: Entity | None = None
        self.quality = {"belt": True, "trails": True, "sky": True, "labels": True}
        ring = _tex("select_ring.png")
        self.reticle = Entity(parent=self.parent, model="quad", scale=3.0,
                              texture=ring, billboard=True, unlit=True,
                              color=color.rgba(0.45, 0.92, 1.0, 0.9),
                              enabled=False)
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

    def ensure_bodies(self, sim) -> None:
        """Create entities for campaign-only bodies (the comet) on demand,
        and leave existing ones alone."""
        for key, body in sim.bodies.items():
            if key == "nix" or key in self.body_entities:
                continue
            self._build_body(key, body)

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

    def _orbit_points_from_elements(self, elements, samples: int = 192):
        """Sample one full period of an orbit in AU (works for campaign
        bodies and perturbed orbits alike -- rings always match the physics)."""
        from ..config import MU_SUN
        from ..maths import windows as window_solver

        period = 2.0 * math.pi * math.sqrt(abs(elements.a) ** 3 / MU_SUN)
        pts = []
        for i in range(samples):
            _, r = window_solver.body_state(elements, MU_SUN, period * i / samples)
            pts.append(r)
        pts.append(pts[0])
        return pts

    def _build_body(self, key: str, body) -> None:
        rgb = body.palette
        entity = Entity(
            parent=self.parent,
            model="sphere",
            scale=0.32 + 0.30 * body.render_scale,
            color=color.rgb(*rgb),
            unlit=True,
        )
        entity.body_key = key  # click-picking looks this up
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

        scene_pts = [au_to_scene(p) for p in self._orbit_points_from_elements(body.elements)]
        line_color = color.rgba(min(1.0, rgb[0] * 1.1), min(1.0, rgb[1] * 1.1),
                                min(1.0, rgb[2] * 1.1), 0.42)
        self.orbit_lines[key] = OrbitLine(scene_pts, line_color, parent=self.parent)

        # Billboard name tag floating above the body.
        tag = _tex(f"label_{key}.png")
        if tag is None:
            from src.utils.procedural import label_texture

            tag_path = os.path.join(_TEX_ROOT, f"label_{key}.png")
            if not os.path.isfile(tag_path):
                from src.utils.procedural import write_png

                write_png(tag_path, label_texture(body.name))
            tag = tag_path
        if tag is not None:
            label = Entity(parent=entity, model="quad",
                           scale=(2.3, 0.41), position=(0, 1.35, 0),
                           texture=tag, billboard=True, unlit=True)
            self.labels[key] = label
        if key == "comet_vigil":
            self._build_comet_tail(entity)

    def _build_comet_tail(self, comet_entity: Entity) -> None:
        """A soft anti-sunward tail; alpha follows the inverse-square glow."""
        tail = Entity(parent=comet_entity, model="quad",
                      scale=(0.9, 7.0, 1.0), position=(0, 0, 0),
                      color=color.rgba(0.55, 0.85, 1.0, 0.0),
                      double_sided=True, unlit=True)
        self.comet_tail = tail

    def _build_asteroid_belt(self) -> None:
        """A few hundred cheap rocks between the belt bodies, for depth.

        All rocks bake into ONE triangle mesh (one draw call, one entity) --
        hundreds of separate entities cost far more than their visual worth.
        """
        if self.belt_mesh is not None:
            return
        rng = random.Random(11)
        vertices: list[Vec3] = []
        for _ in range(260):
            a = rng.uniform(1.35, 2.25)
            angle = rng.uniform(0.0, 2.0 * math.pi)
            drift = rng.uniform(-0.05, 0.05)
            centre = Vec3(a * math.cos(angle), drift, -a * math.sin(angle)) * SCENE_UNITS_PER_AU
            radius = rng.uniform(0.03, 0.12)  # scene units: ~ the old entity scales
            # A lumpy 6-ring sphere, rotated randomly, appended in world space.
            cr, sr = math.cos(rng.uniform(0, 6.3)), math.sin(rng.uniform(0, 6.3))
            tilt = rng.uniform(0.2, 1.0)
            rings, sectors = 5, 8
            grid: list[list[Vec3]] = []
            for r_i in range(rings + 1):
                phi = math.pi * r_i / rings
                ring_row: list[Vec3] = []
                for s_i in range(sectors):
                    th = 2.0 * math.pi * s_i / sectors
                    v = Vec3(math.sin(phi) * math.cos(th),
                             math.cos(phi) * tilt,
                             math.sin(phi) * math.sin(th))
                    v = Vec3(v[0] * cr - v[2] * sr, v[1], v[0] * sr + v[2] * cr)
                    lump = 1.0 + 0.25 * math.sin(5.0 * th + a * 37.0)
                    ring_row.append(centre + v * (radius * lump))
                grid.append(ring_row)
            for r_i in range(rings):
                for s_i in range(sectors):
                    a0 = grid[r_i][s_i]
                    b0 = grid[r_i + 1][s_i]
                    a1 = grid[r_i][(s_i + 1) % sectors]
                    b1 = grid[r_i + 1][(s_i + 1) % sectors]
                    vertices += [a0, b0, a1, b0, b1, a1]
        mesh = Mesh(vertices=vertices, mode="triangle")
        self.belt_mesh = Entity(parent=self.parent, model=mesh,
                                color=color.rgb(0.45, 0.45, 0.52), unlit=True)
        self.belt_mesh.double_sided = False

    def apply_quality(self, **flags: bool) -> None:
        """Toggle expensive eye-candy: belt, trails, skybox, name tags."""
        self.quality.update(flags)
        if self.belt_mesh is not None:
            self.belt_mesh.enabled = self.quality["belt"]
        if self.sky_dome is not None:
            self.sky_dome.enabled = self.quality["sky"]
        for label in self.labels.values():
            label.enabled = self.quality["labels"]
        import src.entities.ship as _ship_module

        _ship_module.TRAILS_ENABLED = self.quality["trails"]

    def _update_comet_tail(self, comet_pos) -> None:
        """Point the tail away from the sun; brighten near perihelion."""
        tail = getattr(self, "comet_tail", None)
        if tail is None or comet_pos is None:
            return
        distance = comet_pos.length()
        if distance < 1e-6:
            return
        away = comet_pos.normalized()
        yaw = math.degrees(math.atan2(away.z, away.x)) - 90.0
        tail.rotation_y = yaw
        # Alpha follows the classic inverse-square comet glow.
        strength = max(0.0, min(1.0, 1.6 / max(0.9, distance) ** 1.6 - 0.05))
        tail.color = color.rgba(0.55, 0.85, 1.0, 0.55 * strength)
        tail.scale = (0.9, 2.0 + 9.0 * strength, 1.0)
        # Slide the sprite outward so it streams behind the nucleus.
        tail.position = Vec3(0, -tail.scale_y / 2.0, 0)

    def set_reticle(self, key: str | None, sim) -> None:
        """Park the selection ring on the targeted body (or hide it)."""
        entity = self.body_entities.get(key) if key else None
        if entity is None:
            self.reticle.enabled = False
            return
        self.reticle.enabled = True
        self.reticle.position = entity.position
        pulse = 1.0 + 0.10 * math.sin(time.time() * 4.0)
        self.reticle.scale = 2.6 * entity.scale_x * pulse

    def make_ship(self, name: str, class_key: str | None = None) -> Freighter:
        ship = Freighter(name, parent=self.parent, class_key=class_key)
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

        self.ensure_bodies(sim)
        comet_pos = None
        for key, entity in self.body_entities.items():
            body = sim.bodies[key] if key in sim.bodies else BODIES[key]
            r, _ = window_solver.body_state(body.elements, MU_SUN, sim.time)
            entity.position = au_to_scene(r)
            entity.rotation_y += 0.15
            if key == "comet_vigil":
                comet_pos = entity.position
        self._update_comet_tail(comet_pos)
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
