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
from .drone import DroneSwarm
import src.entities.drone as _drone_module

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
        self.quality = {
            "belt": True, "trails": True, "sky": True, "labels": True,
            "corona": True, "flares": True, "reticle": True, "orbit_alpha": 0.42,
            "belt_density": 0.55, "ship_lod": "full", "msaa": 2, "vsync": True,
            "bloom": False, "shadows": False, "particles": False,
        }
        ring = _tex("select_ring.png")
        self.reticle = Entity(parent=self.parent, model="quad", scale=3.0,
                              texture=ring, billboard=True, unlit=True,
                              color=color.rgba(0.45, 0.92, 1.0, 0.9),
                              enabled=False)
        self.view_mode = "network"  # network | map | surface
        self.surface_key: str | None = None
        self.surface_props: list = []
        self.map_grid_lines: list = []
        self.atmospheres: dict = {}
        self.swarms: dict = {}  # body_key -> DroneSwarm
        self._map_grid_root = None
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
        # Soft atmosphere shell (readable on high/ultra).
        atmo = Entity(parent=entity, model="sphere",
                      scale=1.18, color=color.rgba(rgb[0], rgb[1], rgb[2], 0.18),
                      unlit=True, double_sided=True)
        self.atmospheres[key] = atmo

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

    def apply_quality(self, **flags) -> None:
        """Toggle eye-candy for the active graphics preset (low..ultra).

        Boolean flags gate whole features. Numeric ones (orbit_alpha,
        belt_density, msaa) scale cost. Display flags (vsync/msaa) are
        applied by the game shell when a real window is up.
        """
        self.quality.update(flags)
        if self.belt_mesh is not None:
            density = float(self.quality.get("belt_density", 1.0) or 0.0)
            self.belt_mesh.enabled = bool(self.quality.get("belt", True)) and density > 0.01
            # Soft scale: low density shrinks the merged belt visually.
            if self.belt_mesh.enabled:
                self.belt_mesh.scale = 0.55 + 0.45 * density
        if self.sky_dome is not None:
            self.sky_dome.enabled = bool(self.quality.get("sky", True))
        for label in self.labels.values():
            label.enabled = bool(self.quality.get("labels", True))
        for glow in getattr(self, "sun_glow", []) or []:
            glow.enabled = bool(self.quality.get("corona", True))
        if hasattr(self, "reticle") and self.reticle is not None:
            # Reticle visibility still follows selection; quality only arms it.
            if not self.quality.get("reticle", True):
                self.reticle.enabled = False
        # Orbit ring alpha scales with the preset so ultra rings pop and low
        # stays quiet on the draw budget.
        alpha = float(self.quality.get("orbit_alpha", 0.42))
        for line in self.orbit_lines.values():
            try:
                c = line.color
                line.color = color.rgba(c.r, c.g, c.b, alpha)
            except Exception:
                pass
        import src.entities.ship as _ship_module

        _ship_module.TRAILS_ENABLED = bool(self.quality.get("trails", True))
        _ship_module.FLARES_ENABLED = bool(self.quality.get("flares", True))
        lod = str(self.quality.get("ship_lod", "full"))
        _ship_module.SHIP_LOD = lod
        for ship in self.ships.values():
            ship.apply_lod(lod)
            # Refresh flare visibility under the new flag.
            ship.set_thrusting(getattr(ship, "_thrusting", False))
        _drone_module.DRONES_FX_ENABLED = bool(self.quality.get("drones_fx", True))
        # Atmosphere shells.
        show_atmo = bool(self.quality.get("atmosphere", True))
        for atmo in self.atmospheres.values():
            atmo.enabled = show_atmo and self.view_mode != "map"
        # Map grid.
        show_grid = bool(self.quality.get("map_grid", True)) and self.view_mode == "map"
        for line in self.map_grid_lines:
            line.enabled = show_grid
        # Surface props detail.
        show_surf = bool(self.quality.get("surface_detail", True)) and self.view_mode == "surface"
        for prop in self.surface_props:
            prop.enabled = show_surf

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
        if entity is None or not self.quality.get("reticle", True):
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


    # -- view modes: network / system map / surface ---------------------------
    def set_view_mode(self, mode: str, body_key: str | None = None, sim=None) -> str:
        """Switch camera presentation mode. Returns the active mode."""
        if mode not in ("network", "map", "surface"):
            mode = "network"
        self.view_mode = mode
        self.surface_key = body_key if mode == "surface" else None
        self._clear_surface_props()
        self._clear_map_grid()
        if mode == "map":
            self._build_map_grid()
            # Flatten-ish: hide surface clutter, keep orbits loud.
            for line in self.orbit_lines.values():
                line.enabled = True
            if self.belt_mesh is not None:
                self.belt_mesh.enabled = bool(self.quality.get("belt", True))
        elif mode == "surface" and body_key:
            self._build_surface_props(body_key, sim)
            for line in self.orbit_lines.values():
                line.enabled = False
            if self.belt_mesh is not None:
                self.belt_mesh.enabled = False
        else:
            for line in self.orbit_lines.values():
                line.enabled = self.orbits_visible
            if self.belt_mesh is not None:
                density = float(self.quality.get("belt_density", 1.0) or 0.0)
                self.belt_mesh.enabled = bool(self.quality.get("belt", True)) and density > 0.01
        # Atmosphere visibility follows mode + quality.
        show_atmo = bool(self.quality.get("atmosphere", True)) and mode != "map"
        for key, atmo in self.atmospheres.items():
            atmo.enabled = show_atmo and (mode != "surface" or key == body_key)
        return mode

    def _clear_surface_props(self) -> None:
        from ursina import destroy
        for prop in self.surface_props:
            try:
                destroy(prop)
            except Exception:
                pass
        self.surface_props.clear()

    def _clear_map_grid(self) -> None:
        from ursina import destroy
        for line in self.map_grid_lines:
            try:
                destroy(line)
            except Exception:
                pass
        self.map_grid_lines.clear()

    def _build_map_grid(self) -> None:
        """AU ring grid for the system chart (top-down map mode)."""
        if not self.quality.get("map_grid", True):
            return
        from ursina import Mesh
        for au in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
            pts = []
            r = au * SCENE_UNITS_PER_AU
            for i in range(65):
                th = 2.0 * math.pi * i / 64
                pts.append(Vec3(r * math.cos(th), 0.02, -r * math.sin(th)))
            mesh = Mesh(vertices=pts, mode="line", thickness=1.0)
            line = Entity(parent=self.parent, model=mesh,
                          color=color.rgba(0.35, 0.55, 0.75, 0.35), unlit=True)
            self.map_grid_lines.append(line)
        # Sun marker cross.
        for axis in (Vec3(2, 0, 0), Vec3(0, 0, 2)):
            mesh = Mesh(vertices=[-axis, axis], mode="line", thickness=2.0)
            line = Entity(parent=self.parent, model=mesh,
                          color=color.rgba(1.0, 0.85, 0.4, 0.7), unlit=True)
            self.map_grid_lines.append(line)

    def _build_surface_props(self, body_key: str, sim=None) -> None:
        """Scatter rocks, vein markers, and a lander pad on the selected body."""
        entity = self.body_entities.get(body_key)
        if entity is None or not self.quality.get("surface_detail", True):
            return
        rng = random.Random(hash(body_key) & 0xFFFFFFFF)
        base = float(entity.scale_x)
        # Ground disc (local "horizon").
        ground = Entity(parent=entity, model="circle", scale=8.0,
                        color=color.rgba(0.15, 0.14, 0.16, 0.95),
                        rotation_x=90, unlit=True, double_sided=True)
        self.surface_props.append(ground)
        # Craggy rocks.
        for _ in range(28):
            ang = rng.uniform(0, math.tau)
            rad = rng.uniform(1.2, 5.5)
            rock = Entity(parent=entity, model="cube",
                          scale=Vec3(rng.uniform(0.15, 0.45),
                                     rng.uniform(0.1, 0.35),
                                     rng.uniform(0.15, 0.45)),
                          position=(rad * math.cos(ang), rng.uniform(0.05, 0.2), rad * math.sin(ang)),
                          rotation=(rng.uniform(0, 40), rng.uniform(0, 360), rng.uniform(0, 40)),
                          color=color.rgb(0.35 + rng.random() * 0.25,
                                         0.32 + rng.random() * 0.2,
                                         0.30 + rng.random() * 0.2),
                          unlit=True)
            self.surface_props.append(rock)
        # Vein beacons (ore colours).
        palette = {
            "ice": (0.6, 0.9, 1.0), "iron": (0.7, 0.45, 0.3), "gold": (0.95, 0.85, 0.2),
            "silver": (0.85, 0.85, 0.9), "platinum": (0.9, 0.9, 0.95),
            "thorite": (0.4, 0.9, 0.35), "aurellium": (1.0, 0.55, 0.15),
            "silicates": (0.75, 0.7, 0.55), "obsidian": (0.2, 0.15, 0.25),
            "helium3": (0.4, 0.85, 1.0), "components": (0.55, 0.6, 0.68),
            "electronics": (0.3, 0.95, 0.8),
        }
        resources = ()
        if sim is not None and body_key in sim.bodies:
            resources = getattr(sim.bodies[body_key], "resources", ()) or ()
        for i, ore in enumerate(resources[:6]):
            rgb = palette.get(ore, (0.8, 0.8, 0.8))
            ang = i * (math.tau / max(1, len(resources))) + 0.4
            beacon = Entity(parent=entity, model="sphere", scale=0.22,
                            position=(2.4 * math.cos(ang), 0.35, 2.4 * math.sin(ang)),
                            color=color.rgb(*rgb), unlit=True)
            beam = Entity(parent=beacon, model="cube", scale=Vec3(0.15, 2.2, 0.15),
                          position=(0, 1.0, 0), color=color.rgba(rgb[0], rgb[1], rgb[2], 0.45), unlit=True)
            self.surface_props.append(beacon)
        # Landing pad.
        pad = Entity(parent=entity, model="cube", scale=Vec3(1.4, 0.08, 1.4),
                     position=(0, 0.06, 0), color=color.rgb(0.25, 0.28, 0.35), unlit=True)
        ring = Entity(parent=pad, model="circle", scale=1.3, position=(0, 0.6, 0),
                      rotation_x=90, color=color.rgba(0.4, 0.9, 1.0, 0.5), unlit=True)
        self.surface_props.append(pad)

    def spawn_swarm(self, body_key: str, count: int, seed: int = 0) -> None:
        """Start or refresh a harvest drone swarm around ``body_key``."""
        entity = self.body_entities.get(body_key)
        if entity is None:
            return
        existing = self.swarms.get(body_key)
        if existing is not None:
            existing.set_count(count)
            return
        self.swarms[body_key] = DroneSwarm(self.parent, entity, count=count, seed=seed)

    def clear_swarm(self, body_key: str | None = None) -> None:
        if body_key is None:
            for key in list(self.swarms):
                self.swarms[key].clear()
                del self.swarms[key]
            return
        swarm = self.swarms.pop(body_key, None)
        if swarm is not None:
            swarm.clear()

    def camera_for_view(self, mode: str, body_key: str | None = None):
        """Return (position, look_at) suggestions for the game camera."""
        if mode == "map":
            return Vec3(0, 95, -1), Vec3(0, 0, 0)
        if mode == "surface" and body_key and body_key in self.body_entities:
            body = self.body_entities[body_key]
            # Sit just above the surface pad looking across the field.
            offset = Vec3(3.5, 2.2, -4.5) * max(0.6, float(body.scale_x))
            return body.position + offset, body.position + Vec3(0, 0.3, 0)
        return Vec3(0, 46, -52), Vec3(0, 0, 0)


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
        # Drone swarms (window harvest).
        for key, swarm in list(self.swarms.items()):
            ent = self.body_entities.get(key)
            if ent is not None:
                swarm.body_entity = ent
            swarm.update(0.016)
        # Surface mode: keep surface body large/centred feel via slow spin only.
        if self.view_mode == "surface" and self.surface_key in self.body_entities:
            self.body_entities[self.surface_key].rotation_y += 0.05
