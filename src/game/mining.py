# Resource and asteroid generation.
import random
from ursina import Vec3, sin, cos
from . import entities, config

def spawn_asteroid_ring(station_entity, count=8, parent=None, region="inner_belt"):
    asteroids = []
    for i in range(count):
        angle = (i / count) * 6.28
        region_info = config.ASTEROID_REGIONS.get(region, config.ASTEROID_REGIONS["inner_belt"])
        r = random.uniform(*region_info["distance"])
        y = random.uniform(-3, 3)
        pos = station_entity.position + Vec3(r * sin(angle), y, r * cos(angle))
        # Select resources by distance: nearby asteroids contain ice or iron; distant ones contain precious metals.
        d = r
        if region == "deep_belt":
            res = random.choices(["gold", "silver", "platinum"], weights=[2, 2, 2])[0]
            amount = random.randint(30, 100)
        elif d < 14:
            res = random.choices(["ice", "iron"], weights=[3, 2])[0]
            amount = random.randint(40, 120)
        elif d < 20:
            res = random.choices(["iron", "silver", "gold"], weights=[2, 2, 1])[0]
            amount = random.randint(30, 100)
        else:
            res = random.choices(["gold", "silver", "platinum"], weights=[2, 2, 1])[0]
            amount = random.randint(20, 80)
        ast = entities.Asteroid(res, amount, pos, parent=parent)
        asteroids.append(ast)
    return asteroids
