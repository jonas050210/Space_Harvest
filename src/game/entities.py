# Detailed 3D objects (Panda3D / Ursina).
# Every model is designed with as much detail as the engine allows.
from ursina import *
from . import config

class Asteroid(Entity):
    """Detailed asteroid with craters, surface detail, glow, and simulated texture."""
    def __init__(self, res_type, amount, position, parent=None):
        # Main body with uneven scaling to simulate an irregular shape.
        super().__init__(
            model='sphere',
            color=color.rgb(*config.RESOURCES[res_type]["color"]),
            scale=Vec3(
                min(1.0 + amount * 0.3, 2.5) * (0.95 + 0.05 * sin(amount)),
                min(1.0 + amount * 0.25, 2.2) * (1.05 - 0.05 * cos(amount * 2)),
                min(1.0 + amount * 0.28, 2.4),
            ),
            position=position,
            parent=parent,
            collider='sphere',
        )
        self.res_type = res_type
        self.amount = amount
        self.initial_amount = max(1, amount)
        self.rotation_speed = Vec3(random.uniform(-20, 20), random.uniform(-15, 15), random.uniform(-25, 25))
        self.label = None

        # Surface detail: small craters as dark points.
        self.craters = []
        for _ in range(12):  # Extra craters for a more detailed appearance.
            crater = Entity(
                model='circle',
                color=color.rgb(30, 30, 40),
                scale=Vec3(0.08, 0.08, 0.01),
                position=position + Vec3(
                    random.uniform(-0.6, 0.6),
                    random.uniform(-0.6, 0.6),
                    random.uniform(-0.8, 0.8)
                ),
                parent=self,
                billboard=True,
            )
            self.craters.append(crater)

        # Glowing rim that simulates atmospheric reflection.
        self.glow = Entity(
            model='sphere',
            color=color.rgba(*[c * 0.3 for c in config.RESOURCES[res_type]["color"]] + [0.15]),
            scale=self.scale * 1.08,
            position=position,
            parent=parent,
        )
        # Resource veins make asteroid value readable before a drone arrives.
        self.veins = []
        vein_color = config.RESOURCES[res_type]["color"]
        for index in range(6):
            vein = Entity(
                model='sphere',
                color=color.rgba(*vein_color, 0.9),
                scale=Vec3(0.11, 0.035, 0.18),
                position=Vec3(random.uniform(-0.55, 0.55), random.uniform(-0.4, 0.4), -0.7),
                rotation=Vec3(random.uniform(-25, 25), random.uniform(-30, 30), random.uniform(-30, 30)),
                parent=self,
            )
            self.veins.append(vein)
        self.update_label()

    def update_label(self):
        text = f"{config.RESOURCES[self.res_type]['name']}\n{int(self.amount)}"
        if self.label is None:
            self.label = Text(
                text=text,
                position=Vec2(0, 0.7),
                origin=(-0.5, -0.5),
                scale=0.9,
                parent=self,
                background=True,
                background_color=color.rgba(0, 0, 0, 0.6),
                color=color.white,
            )
        else:
            self.label.text = text

    def update(self):
        # Slow, stately rotation.
        self.rotation += self.rotation_speed * time.dt
        # The glow ring rotates slightly faster.
        if hasattr(self, 'glow') and self.glow:
            self.glow.rotation += self.rotation_speed * 1.3 * time.dt
        # Keep the label readable and fade resource veins as mining progresses.
        if self.label:
            self.label.rotation_y += time.dt * 5
        depletion = max(0, min(1, self.amount / self.initial_amount))
        for vein in self.veins:
            vein.scale_y = max(0.004, 0.035 * depletion)
            vein.color = color.rgba(vein.color.r, vein.color.g, vein.color.b, int(40 + 215 * depletion))
        self.update_label()
        # Destruction.
        if self.amount <= 0:
            if hasattr(self, 'glow') and self.glow:
                destroy(self.glow)
            for c in self.craters:
                destroy(c)
            for vein in self.veins:
                destroy(vein)
            destroy(self)

class Drone(Entity):
    """Detailed drone with propellers, lights, antenna, and metal texture."""
    def __init__(self, drone_id, parent=None):
        # Main body, softened through scaling.
        super().__init__(
            model='cube',
            color=color.rgb(180, 210, 230),
            scale=Vec3(0.35, 0.18, 0.35),
            position=Vec3(0, 2, 0),
            parent=parent,
            collider='box',
        )
        self.id = drone_id
        self.target = None
        self.cargo = 0

        # Four rotating propellers with additional blades.
        self.propellers = []
        for i in range(4):  # Four blades for a more convincing silhouette.
            prop = Entity(
                model='cube',
                color=color.rgb(55, 60, 70),
                scale=Vec3(0.25, 0.02, 0.05),
                position=Vec3(
                    (0.15 if i % 2 == 0 else -0.15),
                    0.1,
                    (0.15 if i < 2 else -0.15)
                ),
                parent=self,
            )
            self.propellers.append(prop)
        # Additional propeller blades for visual detail.
        self.extra_blades = []
        for i in range(4):
            blade = Entity(
                model='cube',
                color=color.rgb(100, 105, 115),
                scale=Vec3(0.2, 0.015, 0.06),
                position=Vec3(
                    (0.1 if i % 2 == 0 else -0.1),
                    0.08,
                    (0.1 if i < 2 else -0.1)
                ),
                parent=self,
            )
            self.extra_blades.append(blade)

        # Blue-glowing lights.
        self.light_front = Entity(
            model='sphere',
            color=color.cyan,
            scale=Vec3(0.06, 0.06, 0.06),
            position=Vec3(0.15, 0, 0),
            parent=self,
        )
        self.light_back = Entity(
            model='sphere',
            color=color.yellow,
            scale=Vec3(0.05, 0.05, 0.05),
            position=Vec3(-0.15, 0, 0),
            parent=self,
        )

        # Antenna with a red tip.
        self.antenna = Entity(
            model='cube',
            color=color.rgb(55, 60, 70),
            scale=Vec3(0.02, 0.15, 0.02),
            position=Vec3(0, 0.12, 0),
            parent=self,
        )
        self.antenna_tip = Entity(
            model='sphere',
            color=color.red,
            scale=Vec3(0.03, 0.03, 0.03),
            position=Vec3(0, 0.2, 0),
            parent=self,
        )

        # Beam, active only while mining.
        self.beam = Entity(
            model='cube',
            color=color.yellow,
            scale=Vec3(0.02, 0.02, 1),
            position=Vec3(0, 0, 0),
            parent=self,
            enabled=False,
        )
        self.label = Text(
            text=f"D{self.id}",
            position=Vec2(0, 0.3),
            origin=(-0.5, -0.5),
            scale=0.8,
            parent=self,
            background=True,
            background_color=color.rgba(0, 0, 0, 0.5),
            color=color.white,
        )

    def set_role_visual(self, role):
        """Set role colors so players can identify autonomous work at a glance."""
        role_colors = {"miner": color.orange, "hauler": color.azure, "scout": color.cyan}
        role_color = role_colors.get(role, color.white)
        self.light_front.color = role_color
        self.antenna_tip.color = role_color
        self.color = color.rgb(185, 205, 220) if role == "miner" else role_color

    def set_cargo_visual(self, resource_key, amount):
        """Show a resource-colored cargo pod while a drone returns to the station."""
        if not hasattr(self, "cargo_pod"):
            self.cargo_pod = Entity(model="cube", parent=self, position=Vec3(0, -0.14, 0), scale=Vec3(0.18, 0.1, 0.18), enabled=False)
        active = bool(resource_key and amount > 0)
        self.cargo_pod.enabled = active
        if active:
            self.cargo_pod.color = color.rgb(*config.RESOURCES.get(resource_key, config.RESOURCES["iron"])["color"])
            self.cargo_pod.scale = Vec3(0.18, 0.08 + min(0.12, amount / 100), 0.18)

    def update(self):
        # Gentle hovering animation.
        self.y += 0.15 * sin(time.time() * 2 + self.id) * time.dt
        # Rotate every propeller blade.
        for prop in self.propellers:
            prop.rotation_z += 600 * time.dt
        for blade in self.extra_blades:
            blade.rotation_z += 600 * time.dt
        # Antenne leuchtet easy
        self.light_front.scale = Vec3(0.06 + 0.02 * sin(time.time() * 8), 0.06 + 0.02 * sin(time.time() * 8), 0.06)

class StationPart(Entity):
    """Ultrarealistische Raumstation: Module, Fenster, Antennen, Metallschimmer."""
    def __init__(self, parent=None):
        super().__init__(
            model='cube',
            color=color.rgb(60, 65, 75),
            scale=Vec3(2.5, 1.2, 2.5),
            position=Vec3(0, 0.5, 0),
            parent=parent,
            collider='box',
        )
        # Modules represented by small expansion cubes.
        self.modules = []
        for i in range(4):
            mod = Entity(
                model='cube',
                color=color.rgb(45, 50, 60),
                scale=Vec3(0.6, 0.4, 0.6),
                position=Vec3(
                    0.9 if i % 2 == 0 else -0.9,
                    0.6,
                    0.9 if i < 2 else -0.9
                ),
                parent=self,
            )
            # Module details: windows as small yellow points.
            window_dots = []
            for w in range(3):
                dot = Entity(
                    model='sphere',
                    color=color.yellow,
                    scale=Vec3(0.05, 0.05, 0.01),
                    position=Vec3(0, 0, 0.3),
                    parent=mod,
                )
                window_dots.append(dot)
            self.modules.append(mod)

        # Antenna: thin cylinder with a red tip.
        self.antenna = Entity(
            model='cube',
            color=color.rgb(55, 60, 70),
            scale=Vec3(0.04, 0.8, 0.04),
            position=Vec3(0, 1.1, 0),
            parent=self,
        )
        self.antenna_tip = Entity(
            model='sphere',
            color=color.red,
            scale=Vec3(0.08, 0.08, 0.08),
            position=Vec3(0, 1.5, 0),
            parent=self,
        )

        # Landing legs: four thin cylinders.
        self.legs = []
        for leg_pos in [Vec3(0.8, -0.6, 0.8), Vec3(-0.8, -0.6, 0.8), Vec3(0.8, -0.6, -0.8), Vec3(-0.8, -0.6, -0.8)]:
            leg = Entity(
                model='cube',
                color=color.rgb(55, 60, 70),
                scale=Vec3(0.08, 0.6, 0.08),
                position=leg_pos,
                parent=self,
            )
            self.legs.append(leg)

    def update(self):
        """Pulse practical lights to make the colony feel operational."""
        pulse = 0.75 + 0.25 * sin(time.time() * 2)
        self.antenna_tip.scale = Vec3(0.07 * pulse, 0.07 * pulse, 0.07 * pulse)
        for module in self.modules:
            for window in module.children:
                if getattr(window, "model", None) == "sphere":
                    window.color = color.rgba(255, 210, 90, int(180 + 75 * pulse))

class BlackHole(Entity):
    """Detailed black hole with a rotating ring, glow, and gravity effect."""
    def __init__(self, position, parent=None):
        super().__init__(
            model='circle',
            color=color.black,
            scale=Vec3(3, 3, 3),
            position=position,
            parent=parent,
            collider='sphere',
        )
        # Rotating accretion ring with a color gradient.
        self.ring = Entity(
            model='circle',
            color=color.rgb(145, 80, 220),
            scale=Vec3(1.8, 1.8, 1.8),
            position=position,
            parent=parent,
        )
        # Additional inner ring for visual detail.
        self.inner_ring = Entity(
            model='circle',
            color=color.rgba(128, 0, 128, 0.6),
            scale=Vec3(1.2, 1.2, 1.2),
            position=position,
            parent=parent,
        )
        # Glowing particles around the black hole.
        self.particles = []
        for _ in range(20):
            p = Entity(
                model='sphere',
                color=color.rgba(200, 100, 255, 0.8),
                scale=Vec3(0.04, 0.04, 0.04),
                position=position + Vec3(
                    random.uniform(-2, 2),
                    random.uniform(-2, 2),
                    random.uniform(-2, 2)
                ),
                parent=parent,
            )
            self.particles.append(p)

    def update(self):
        # Rotierende Ringe
        self.ring.rotation_z += 30 * time.dt
        self.inner_ring.rotation_z -= 50 * time.dt
        # Partikel bewegen sich easy
        for p in self.particles:
            p.position += Vec3(0.02 * sin(time.time() * 2 + random.random()), 0.01, 0.02 * cos(time.time() * 2 + random.random())) * time.dt

class ConveyorBelt(Entity):
    """Detailed conveyor belt with moving points, lights, and metal texture."""
    def __init__(self, start_pos, end_pos, parent=None):
        mid = (start_pos + end_pos) * 0.5
        length = (end_pos - start_pos).length()
        super().__init__(
            model='cube',
            color=color.rgb(100, 110, 130),
            scale=Vec3(length, 0.15, 0.25),
            position=mid,
            parent=parent,
        )
        self.look_at(end_pos)
        # Bewegliche Punkte (gelb, leuchtend)
        self.belt_dots = []
        for i in range(6):
            dot = Entity(
                model='sphere',
                color=color.yellow,
                scale=Vec3(0.06, 0.06, 0.06),
                position=Vec3(i * (length / 5) - length / 2, 0.12, 0),
                parent=self,
            )
            self.belt_dots.append(dot)
        # Cyan side lights.
        self.side_lights = []
        for side in [Vec3(0, 0.1, 0.12), Vec3(0, 0.1, -0.12)]:
            light = Entity(
                model='sphere',
                color=color.cyan,
                scale=Vec3(0.03, 0.03, 0.03),
                position=side,
                parent=self,
            )
            self.side_lights.append(light)

    def set_resource_visual(self, resource_key):
        """Color moving logistics packets by their destination resource."""
        packet_color = config.RESOURCES.get(resource_key, config.RESOURCES["iron"])["color"]
        for dot in self.belt_dots:
            dot.color = color.rgb(*packet_color)

    def update(self):
        for dot in self.belt_dots:
            dot.position += Vec3(0.08, 0, 0) * time.dt
            # Return a point to the start after it reaches the end.
            if dot.position.x > self.scale.x / 2:
                dot.position.x = -self.scale.x / 2
        # Pulse the lights.
        for light in self.side_lights:
            light.scale = Vec3(0.03 + 0.01 * sin(time.time() * 4), 0.03 + 0.01 * sin(time.time() * 4), 0.03)

class AlienShip(Entity):
    """Detailed hostile ship with metal texture, red lights, and propellers."""
    def __init__(self, position, parent=None):
        super().__init__(
            model='diamond',
            color=color.rgb(180, 20, 20),
            scale=Vec3(0.9, 0.45, 0.9),
            position=position,
            parent=parent,
            collider='diamond',
        )
        self.health = 20
        self.speed = 1.5
        # Propeller (rotierend, hinten)
        self.propeller = Entity(
            model='cube',
            color=color.rgb(55, 60, 70),
            scale=Vec3(0.2, 0.05, 0.1),
            position=Vec3(0, 0, -0.4),
            parent=self,
        )
        # Red front lights.
        self.lights = []
        for lx in [-0.2, 0.2]:
            l = Entity(
                model='sphere',
                color=color.red,
                scale=Vec3(0.04, 0.04, 0.04),
                position=Vec3(lx, 0.1, 0.3),
                parent=self,
            )
            self.lights.append(l)

    def update(self):
        self.propeller.rotation_z += 400 * time.dt
        for l in self.lights:
            l.scale = Vec3(0.04 + 0.01 * sin(time.time() * 10), 0.04 + 0.01 * sin(time.time() * 10), 0.04)

class LaserBeam(Entity):
    """Detailed laser beam with glow, pulses, and particles."""
    def __init__(self, start_pos, end_pos, parent=None):
        mid = (start_pos + end_pos) * 0.5
        length = (end_pos - start_pos).length()
        super().__init__(
            model='cube',
            color=color.rgba(255, 255, 100, 200),
            scale=Vec3(0.04, 0.04, length),
            position=mid,
            parent=parent,
        )
        self.look_at(end_pos)
        self.core = Entity(model="cube", color=color.white, scale=Vec3(0.012, 0.012, length * 1.02), parent=self)
        self.impact_glow = Entity(model="sphere", color=color.rgba(255, 220, 90, 180), scale=0.13, position=Vec3(0, 0, length / 2), parent=self)
        # Small glowing particles along the beam.
        self.particles = []
        for i in range(5):
            p = Entity(
                model='sphere',
                color=color.yellow,
                scale=Vec3(0.03, 0.03, 0.03),
                position=Vec3(0, 0, (i - 2) * (length / 4)),
                parent=self,
            )
            self.particles.append(p)

    def update(self):
        pulse = 0.8 + 0.2 * sin(time.time() * 18)
        self.core.scale = Vec3(0.012 * pulse, 0.012 * pulse, self.scale.z * 1.02)
        self.impact_glow.scale = Vec3(0.1 + 0.05 * pulse, 0.1 + 0.05 * pulse, 0.1 + 0.05 * pulse)
        for index, particle in enumerate(self.particles):
            particle.position.y = sin(time.time() * 12 + index) * 0.025

class MiningImpact(Entity):
    """Short-lived mining impact with resource-colored sparks and debris."""
    def __init__(self, position, resource_key, parent=None):
        resource_color = config.RESOURCES.get(resource_key, config.RESOURCES["iron"])["color"]
        super().__init__(model="sphere", color=color.rgba(*resource_color, 0.95), scale=0.12, position=position, parent=parent)
        self.life = 0.28
        self.fragments = []
        for _ in range(7):
            fragment = Entity(
                model="sphere",
                color=color.rgba(*resource_color, 0.85),
                scale=random.uniform(0.018, 0.045),
                position=position,
                parent=parent,
            )
            fragment.velocity = Vec3(random.uniform(-1.4, 1.4), random.uniform(0.2, 1.8), random.uniform(-1.4, 1.4))
            self.fragments.append(fragment)

    def update(self):
        self.life -= time.dt
        self.scale += Vec3(0.45, 0.45, 0.45) * time.dt
        self.color = color.rgba(self.color.r, self.color.g, self.color.b, max(0, int(self.life * 850)))
        for fragment in self.fragments:
            fragment.position += fragment.velocity * time.dt
            fragment.velocity.y -= 2.5 * time.dt
            fragment.scale *= 0.96
        if self.life <= 0:
            for fragment in self.fragments:
                destroy(fragment)
            destroy(self)

class Planet(Entity):
    """Low-cost scenic planet with a colored atmosphere and optional rings."""
    def __init__(self, name, position, planet_color, scale=8, rings=False, parent=None):
        super().__init__(model="sphere", color=color.rgb(*planet_color), scale=scale, position=position, parent=parent)
        self.name = name
        self.atmosphere = Entity(model="sphere", color=color.rgba(*planet_color, 0.15), scale=1.08, parent=self)
        self.rings = Entity(model="circle", color=color.rgba(180, 170, 220, 0.4), scale=1.8, rotation_x=68, parent=self, enabled=rings)

    def update(self):
        self.rotation_y += 0.35 * time.dt
        self.atmosphere.scale = 1.075 + 0.01 * sin(time.time() * 0.4)
        if self.rings.enabled:
            self.rings.rotation_z += 0.12 * time.dt


class TradeFreighter(Entity):
    """A slow, friendly industrial freighter that visually represents trade activity."""
    def __init__(self, start, destination, parent=None):
        super().__init__(model="cube", color=color.rgb(100, 130, 155), scale=Vec3(1.2, 0.35, 0.55), position=start, parent=parent)
        self.destination = destination
        self.navigation_light = Entity(model="sphere", color=color.cyan, scale=0.09, position=Vec3(0.55, 0, 0), parent=self)
        self.cargo_lights = [Entity(model="sphere", color=color.orange, scale=0.06, position=Vec3(-0.3 + index * 0.2, 0.15, 0), parent=self) for index in range(3)]

    def update(self):
        direction = self.destination - self.position
        if direction.length() > 1:
            self.position += direction.normalize() * 1.8 * time.dt
            self.look_at(self.destination)
        self.navigation_light.scale = Vec3(0.07 + 0.03 * sin(time.time() * 4), 0.07 + 0.03 * sin(time.time() * 4), 0.07)


class RogueMiningDrone(Entity):
    """Non-combat deep-space hazard: a silent automated relic with a warning beacon."""
    def __init__(self, position, parent=None):
        super().__init__(model="diamond", color=color.rgb(80, 65, 85), scale=Vec3(0.55, 0.22, 0.55), position=position, parent=parent)
        self.warning_light = Entity(model="sphere", color=color.red, scale=0.07, position=Vec3(0, 0.14, 0), parent=self)

    def update(self):
        self.rotation_y += 20 * time.dt
        pulse = 0.7 + 0.3 * sin(time.time() * 6)
        self.warning_light.scale = Vec3(0.05 * pulse, 0.05 * pulse, 0.05 * pulse)

class StationModuleUnit(Entity):
    """Placed module visual with a lightweight function-specific activity effect."""
    COLORS = {
        "solar_panel": color.azure,
        "refinery": color.orange,
        "storage": color.yellow,
        "life_support": color.cyan,
        "research_observatory": color.rgb(0, 180, 170),
        "orbital_trade_hub": color.green,
        "deep_belt_outpost": color.rgb(145, 80, 220),
    }

    def __init__(self, module_key, position, parent=None):
        super().__init__(model="cube", color=self.COLORS.get(module_key, color.azure), scale=(0.7, 0.45, 0.7), position=position, parent=parent)
        self.module_key = module_key
        self.signal = Entity(model="sphere", color=self.color, scale=0.12, position=Vec3(0, 0.3, 0), parent=self)
        self.solar_wing = Entity(model="cube", color=color.rgb(55, 95, 140), scale=(1.25, 0.035, 0.3), position=Vec3(0, 0.28, 0), parent=self, enabled=module_key == "solar_panel")
        self.exhaust = Entity(model="sphere", color=color.rgba(255, 125, 45, 100), scale=0.12, position=Vec3(0, 0.45, -0.18), parent=self, enabled=module_key == "refinery")
        self.dock_lights = [Entity(model="sphere", color=color.cyan, scale=0.05, position=Vec3(x, 0.1, 0.38), parent=self, enabled=module_key == "orbital_trade_hub") for x in (-0.22, 0.22)]

    def update(self):
        pulse = 0.75 + 0.25 * sin(time.time() * 3)
        self.signal.scale = Vec3(0.09 + 0.05 * pulse, 0.09 + 0.05 * pulse, 0.09 + 0.05 * pulse)
        if self.solar_wing.enabled:
            self.solar_wing.rotation_y += 8 * time.dt
        if self.exhaust.enabled:
            self.exhaust.y = 0.45 + 0.07 * sin(time.time() * 4)
            self.exhaust.scale = Vec3(0.1 + 0.05 * pulse, 0.1 + 0.05 * pulse, 0.1 + 0.05 * pulse)
        for light in self.dock_lights:
            light.scale = Vec3(0.04 + 0.03 * pulse, 0.04 + 0.03 * pulse, 0.04 + 0.03 * pulse)
