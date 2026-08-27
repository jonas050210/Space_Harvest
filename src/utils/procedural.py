"""Procedural asset generation.

Everything here is generated rather than downloaded, so the repository stays
tiny and there is no build step that depends on a third-party host. Two
outputs:

``write_uv_sphere``
    A UV sphere as a Wavefront ``.obj`` with normals and UVs, suitable for
    planets and asteroid stand-ins.

``write_planet_texture``
    A banded, cratered planet texture written as a PNG. Value noise is done
    with numpy only, so there is no dependency beyond numpy itself.
"""

from __future__ import annotations

import math
import os

import numpy as np


def write_uv_sphere(path: str, radius: float = 1.0, rings: int = 24, sectors: int = 36) -> str:
    """Write a UV sphere to ``path`` as an ``.obj`` and return the path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    vertices: list[str] = []
    normals: list[str] = []
    uvs: list[str] = []
    faces: list[str] = []

    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(sectors + 1):
            theta = 2.0 * math.pi * s / sectors
            x = math.sin(phi) * math.cos(theta)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(theta)
            vertices.append(f"v {x * radius:.6f} {y * radius:.6f} {z * radius:.6f}")
            normals.append(f"vn {x:.6f} {y:.6f} {z:.6f}")
            uvs.append(f"vt {s / sectors:.6f} {1.0 - r / rings:.6f}")

    stride = sectors + 1
    for r in range(rings):
        for s in range(sectors):
            a = r * stride + s + 1
            b = a + stride
            faces.append(f"f {a}/{a}/{a} {b}/{b}/{b} {a + 1}/{a + 1}/{a + 1}")
            faces.append(f"f {b}/{b}/{b} {b + 1}/{b + 1}/{b + 1} {a + 1}/{a + 1}/{a + 1}")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Procedurally generated UV sphere\n")
        handle.write(f"# rings={rings} sectors={sectors} radius={radius}\n")
        handle.write("\n".join(vertices))
        handle.write("\n")
        handle.write("\n".join(normals))
        handle.write("\n")
        handle.write("\n".join(uvs))
        handle.write("\n")
        handle.write("\n".join(faces))
        handle.write("\n")
    return path


def _value_noise(size: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    """Bilinear-interpolated value noise on a ``size x size`` grid."""
    grid = rng.random((cells + 1, cells + 1))
    xs = np.linspace(0.0, cells, size, endpoint=False)
    ys = np.linspace(0.0, cells, size, endpoint=False)
    x0 = xs.astype(int)
    y0 = ys.astype(int)
    fx = (xs - x0).reshape(1, -1)
    fy = (ys - y0).reshape(-1, 1)

    top_left = grid[y0[:, None], x0[None, :]]
    top_right = grid[y0[:, None], (x0 + 1)[None, :]]
    bottom_left = grid[(y0 + 1)[:, None], x0[None, :]]
    bottom_right = grid[(y0 + 1)[:, None], (x0 + 1)[None, :]]

    smooth_x = fx * fx * (3.0 - 2.0 * fx)
    smooth_y = fy * fy * (3.0 - 2.0 * fy)
    top = top_left + (top_right - top_left) * smooth_x
    bottom = bottom_left + (bottom_right - bottom_left) * smooth_x
    return top + (bottom - top) * smooth_y


def planet_texture(size: int = 512, seed: int = 20260826,
                   base: tuple[float, float, float] = (0.45, 0.36, 0.30),
                   accent: tuple[float, float, float] = (0.72, 0.62, 0.50)) -> np.ndarray:
    """Return an ``(size, size, 3)`` uint8 planet texture.

    Layered value noise gives terrain mottling, a latitude term adds polar
    banding, and a handful of circular features read as craters at game zoom.
    """
    rng = np.random.default_rng(seed)
    height = np.zeros((size, size), dtype=float)
    amplitude = 1.0
    total = 0.0
    for octave, cells in enumerate((6, 12, 24, 48)):
        height += amplitude * _value_noise(size, cells, rng)
        total += amplitude
        amplitude *= 0.5
    height /= total

    # Polar banding, mild so the body still reads as rock rather than gas.
    latitude = np.linspace(-1.0, 1.0, size).reshape(-1, 1)
    height = 0.75 * height + 0.25 * (1.0 - np.abs(latitude))

    # Craters: darken a disc and brighten its rim.
    for _ in range(26):
        cx, cy = rng.integers(0, size, size=2)
        crater_radius = float(rng.integers(6, max(8, size // 18)))
        yy, xx = np.ogrid[:size, :size]
        distance = np.hypot(xx - cx, yy - cy)
        floor = distance < crater_radius
        rim = (distance >= crater_radius) & (distance < crater_radius * 1.22)
        height[floor] -= 0.16
        height[rim] += 0.10

    # ndarray.ptp() was removed in NumPy 2.0, so use the module-level form.
    height = np.clip((height - height.min()) / max(1e-6, float(np.ptp(height))), 0.0, 1.0)

    base_array = np.array(base, dtype=float).reshape(1, 1, 3)
    accent_array = np.array(accent, dtype=float).reshape(1, 1, 3)
    image = base_array + (accent_array - base_array) * height[..., None]
    # Slight limb darkening baked into the texture for cheap shading.
    image *= (0.85 + 0.15 * height[..., None])
    return np.clip(image * 255.0, 0, 255).astype(np.uint8)


def write_png(path: str, image: np.ndarray) -> str:
    """Write an ``(H, W, 3)`` uint8 array as a PNG using Pillow."""
    from PIL import Image

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(image).save(path)
    return path


def build_all(asset_root: str) -> dict[str, str]:
    """Generate every asset the prototype ships with. Returns name -> path."""
    outputs: dict[str, str] = {}
    outputs["sphere.obj"] = write_uv_sphere(os.path.join(asset_root, "models", "sphere.obj"))
    outputs["asteroid.obj"] = write_uv_sphere(
        os.path.join(asset_root, "models", "asteroid.obj"), radius=1.0, rings=14, sectors=20
    )
    outputs["planet_surface.png"] = write_png(
        os.path.join(asset_root, "textures", "planet_surface.png"),
        planet_texture(512, seed=20260826),
    )
    outputs["ice_moon.png"] = write_png(
        os.path.join(asset_root, "textures", "ice_moon.png"),
        planet_texture(512, seed=99, base=(0.55, 0.72, 0.85), accent=(0.90, 0.96, 1.0)),
    )
    return outputs


if __name__ == "__main__":
    # src/utils/procedural.py -> the project root is three levels up, so the
    # assets land in <project>/assets rather than <project>/src/assets.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.join(project_root, "assets")
    for name, path in build_all(root).items():
        print(f"  {name:22s} {os.path.getsize(path) / 1024.0:7.1f} KB  {path}")
