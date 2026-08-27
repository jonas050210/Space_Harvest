# Detailed 3D scene.
import random
from ursina import *
from . import entities, mining, config

def build_scene(station_entity, parent=None):
    # Background stars with varying sizes and brightness.
    stars = []
    for _ in range(300):
        brightness = random.uniform(0.6, 1.0)
        size = random.uniform(0.02, 0.15)
        star = Entity(
            model='sphere',
            color=color.rgb(brightness, brightness, brightness * 0.95),
            scale=size,
            position=Vec3(
                random.uniform(-60, 60),
                random.uniform(-40, 40),
                random.uniform(-80, -10)
            ),
            parent=parent,
        )
        stars.append(star)
    # Nebulae simulated with large translucent circles.
    nebulae = []
    for _ in range(5):
        nebula = Entity(
            model='circle',
            color=color.rgba(0.3, 0.2, 0.5, 0.05),
            scale=random.uniform(15, 35),
            position=Vec3(
                random.uniform(-50, 50),
                random.uniform(-20, 20),
                random.uniform(-70, -30)
            ),
            parent=parent,
        )
        nebulae.append(nebula)
    return stars

def setup_camera():
    camera.position = Vec3(0, 22, -28)
    camera.rotation_x = 38
    camera.rotation_y = 0

def update_scene(stars, nebulae):
    # Slowly rotate stars and nebulae for a more immersive effect.
    for star in stars:
        star.rotation_y += 0.3 * time.dt
    for nebula in nebulae:
        nebula.rotation_z += 0.1 * time.dt


def set_region_atmosphere(stars, region):
    """Apply a subtle, low-cost palette shift for the active asteroid region."""
    palettes = {
        "inner_belt": (0.9, 0.95, 1.0),
        "metallic_belt": (0.75, 0.8, 0.95),
        "deep_belt": (0.65, 0.45, 0.95),
    }
    red, green, blue = palettes.get(region, palettes["inner_belt"])
    for star in stars:
        star.color = color.rgba(red, green, blue, 0.9)
