"""Harvest drone visuals -- the hundred-strong window swarm.

Lightweight billboard/needle meshes so a full GO-launch of 100 drones stays
inside the RTX 4060 Ti budget. Quality preset ``drones_fx`` can hide them.
"""

from __future__ import annotations

import math
import random

from ursina import Entity, Vec3, color, destroy


DRONES_FX_ENABLED = True


class DroneSwarm:
    """A cloud of harvest drones orbiting / skimming a body during a swarm."""

    def __init__(self, parent, body_entity, count: int = 24, seed: int = 0):
        self.parent = parent
        self.body_entity = body_entity
        self.drones: list[Entity] = []
        self._phase = 0.0
        self._rng = random.Random(seed)
        self.count = max(0, min(100, int(count)))
        self._build()

    def _build(self) -> None:
        self.clear()
        if not DRONES_FX_ENABLED or self.body_entity is None or self.count <= 0:
            return
        base = float(getattr(self.body_entity, "scale_x", 1.0) or 1.0)
        for i in range(self.count):
            # Needle hull + cyan engine tip -- reads as a designed craft at distance.
            drone = Entity(parent=self.parent, model="cube",
                           scale=Vec3(0.04, 0.04, 0.14),
                           color=color.rgb(0.55, 0.92, 1.0), unlit=True)
            tip = Entity(parent=drone, model="sphere", scale=Vec3(0.7, 0.7, 0.5),
                         position=(0, 0, 0.55), color=color.rgb(0.3, 1.0, 0.85), unlit=True)
            wing = Entity(parent=drone, model="cube", scale=Vec3(0.9, 0.08, 0.25),
                          position=(0, 0, -0.1), color=color.rgb(0.75, 0.88, 1.0), unlit=True)
            drone._tip = tip
            drone._wing = wing
            # Stable orbital parameters around the body.
            drone._radius = base * self._rng.uniform(1.8, 4.2)
            drone._incl = self._rng.uniform(-0.55, 0.55)
            drone._speed = self._rng.uniform(0.7, 1.8) * (1.0 if i % 2 == 0 else -1.0)
            drone._offset = self._rng.uniform(0.0, math.tau)
            drone._bob = self._rng.uniform(0.4, 1.2)
            self.drones.append(drone)

    def set_count(self, count: int) -> None:
        count = max(0, min(100, int(count)))
        if count == self.count and self.drones:
            return
        self.count = count
        self._build()

    def update(self, dt_real: float = 0.016) -> None:
        if not self.drones or self.body_entity is None:
            return
        if not DRONES_FX_ENABLED:
            for d in self.drones:
                d.enabled = False
            return
        centre = self.body_entity.position
        self._phase += dt_real
        for drone in self.drones:
            drone.enabled = True
            ang = drone._offset + self._phase * drone._speed
            x = math.cos(ang) * drone._radius
            z = math.sin(ang) * drone._radius
            y = math.sin(ang * drone._bob + drone._offset) * drone._radius * 0.25 + drone._incl * drone._radius
            drone.position = centre + Vec3(x, y, z)
            # Point roughly along the flight tangent.
            drone.look_at(centre + Vec3(-math.sin(ang), 0, math.cos(ang)))
            # Engine tip pulse.
            pulse = 0.5 + 0.5 * math.sin(self._phase * 6.0 + drone._offset)
            try:
                drone._tip.color = color.rgba(0.3, 1.0, 0.85, 0.55 + 0.45 * pulse)
            except Exception:
                pass

    def clear(self) -> None:
        for drone in self.drones:
            try:
                destroy(drone)
            except Exception:
                pass
        self.drones.clear()
