# Utility functions.
import random, math
from ursina import Vec3

def lerp(a, b, t):
    return a + (b - a) * t

def random_color():
    return Vec3(random.random(), random.random(), random.random())
