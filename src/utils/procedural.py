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
import zlib

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
    """Write an ``(H, W, 3)``/``(H, W, 4)`` uint8 array as a PNG using Pillow."""
    from PIL import Image

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(np.ascontiguousarray(image.astype("uint8"))).save(path)
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
    outputs.update(write_game_textures(asset_root))
    return outputs


# ---------------------------------------------------------------------------
# Game textures: stylised skybox, planets, glows (generated, committed once)
# ---------------------------------------------------------------------------

#: body key -> (base colour, accent colour) for the stylised look
GAME_BODY_PALETTES = {
    "colony": ((0.30, 0.55, 0.75), (0.55, 0.85, 0.60)),   # blue ocean + green land
    "inner_belt": ((0.55, 0.55, 0.58), (0.75, 0.72, 0.70)),
    "metallic_belt": ((0.38, 0.42, 0.52), (0.62, 0.68, 0.78)),
    "gas_giant_orbit": ((0.62, 0.40, 0.82), (0.85, 0.66, 0.95)),
    "deep_belt": ((0.42, 0.32, 0.62), (0.66, 0.50, 0.88)),
    "derelict_zone": ((0.48, 0.30, 0.22), (0.72, 0.50, 0.34)),
    "nix": ((0.78, 0.86, 0.95), (0.95, 0.98, 1.0)),
    # Campaign bodies (ops layer installs these; textures are style-only).
    "comet_vigil": ((0.45, 0.60, 0.78), (0.85, 0.94, 1.0)),
    "trojan_field": ((0.50, 0.62, 0.44), (0.82, 0.92, 0.76)),
    "cinder_moon": ((0.55, 0.16, 0.10), (0.95, 0.45, 0.28)),
    "outer_reach": ((0.20, 0.32, 0.58), (0.45, 0.65, 1.0)),
    "frost_ring": ((0.45, 0.62, 0.80), (0.80, 0.93, 1.0)),
    "ember_shoal": ((0.58, 0.22, 0.08), (1.0, 0.52, 0.24)),
    "l5_garden": ((0.26, 0.55, 0.34), (0.55, 0.90, 0.66)),
    "hearthwreck": ((0.36, 0.32, 0.28), (0.68, 0.60, 0.52)),
    "night_well": ((0.12, 0.16, 0.30), (0.30, 0.38, 0.65)),
    # The Far Charter (v1.6).
    "sungrazer": ((0.62, 0.36, 0.10), (1.0, 0.75, 0.32)),
    "vagrant": ((0.22, 0.50, 0.46), (0.50, 0.90, 0.82)),
    "boreas": ((0.32, 0.38, 0.62), (0.68, 0.75, 1.0)),
}

#: bodies rendered with the banded gas-giant texture instead of planet_texture.
GAS_GIANT_TEXTURE_KEYS = ("gas_giant_orbit", "boreas")


def starfield_texture(width: int = 1024, height: int = 512, seed: int = 7,
                     n_stars: int = 2600) -> np.ndarray:
    """Dark space backdrop with a nebula wash and a power-law star mix."""
    rng = np.random.default_rng(seed)
    image = np.zeros((height, width, 3), dtype=float)

    # Deep-space floor so no corner is pure black, then the nebula wash.
    image[..., 0] += 8.0
    image[..., 1] += 7.0
    image[..., 2] += 14.0
    wash_a = _value_noise(max(width, height), 5, rng)[:height, :width]
    wash_b = _value_noise(max(width, height), 3, rng)[:height, :width]
    image[..., 0] += 40.0 * wash_a + 16.0 * wash_b
    image[..., 1] += 22.0 * wash_a + 10.0 * wash_b
    image[..., 2] += 62.0 * wash_a + 28.0 * wash_b

    # Stars: brightness follows a power law; a few get colour and flare.
    for _ in range(n_stars):
        x = int(rng.integers(0, width))
        y = int(rng.integers(0, height))
        bright = rng.random() ** 2.2
        tint = np.array([1.0, 1.0, 1.0])
        roll = rng.random()
        if roll < 0.12:
            tint = np.array([0.72, 0.84, 1.0])    # hot blue
        elif roll < 0.22:
            tint = np.array([1.0, 0.85, 0.62])    # ember orange
        pixel = np.clip(bright * 255.0, 40.0, 255.0)
        image[y, x] = np.minimum(255.0, image[y, x] + pixel * tint)
        if bright > 0.80:  # bright stars get a small cross flare
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = (x + dx) % width, (y + dy) % height
                image[yy, xx] = np.minimum(255.0, image[yy, xx] + pixel * 0.30 * tint)
            if bright > 0.94:
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                    xx, yy = (x + dx) % width, (y + dy) % height
                    image[yy, xx] = np.minimum(255.0, image[yy, xx] + pixel * 0.15 * tint)
    return np.clip(image, 0, 255).astype("uint8")


def gas_giant_texture(width: int = 256, height: int = 128, seed: int = 5,
                      base: tuple = (0.62, 0.40, 0.82),
                      accent: tuple = (0.88, 0.70, 0.96)) -> np.ndarray:
    """Stylised banded gas giant: wavy latitude stripes plus a great spot."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    v = yy / max(1, height - 1)
    # Per-pixel wobble: distort the latitude by smooth noise so the bands
    # ripple instead of running dead straight.
    wobble = _value_noise(max(width, height), 12, rng)[:height, :width] - 0.5
    wobble += 0.5 * (_value_noise(max(width, height), 26, rng)[:height, :width] - 0.5)
    band = 0.5 + 0.5 * np.sin(v * math.pi * 9.0 + 4.5 * wobble)
    # Fine streaks along the flow direction.
    streak = _value_noise(max(width, height), 40, rng)[:height, :width]
    band = np.clip(band + 0.12 * (streak - 0.5), 0.0, 1.0)
    base_c, accent_c = np.array(base), np.array(accent)
    rows = (base_c[None, None, :] * (1.0 - 0.6 * band[..., None])
            + accent_c[None, None, :] * (0.6 * band[..., None])) * 255.0
    # Great spot: a soft oval in the lower third.
    cx, cy, rx, ry = int(width * 0.66), int(height * 0.68), int(width * 0.10), int(height * 0.12)
    spot = np.clip(1.0 - np.hypot((xx - cx) / rx, (yy - cy) / ry), 0.0, 1.0) ** 1.4
    rows += spot[..., None] * (accent_c[None, None, :] * 255.0 - rows) * 0.85
    return np.clip(rows, 0, 255).astype("uint8")


def glow_sprite(size: int = 128, colour: tuple = (255, 214, 140),
                hardness: float = 2.2) -> np.ndarray:
    """RGBA radial glow, for sun halos, engine flares and selection rings."""
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - size / 2, yy - size / 2) / (size / 2)
    alpha = np.clip(1.0 - r, 0.0, 1.0) ** hardness
    image = np.zeros((size, size, 4), dtype=float)
    image[..., 0] = colour[0]
    image[..., 1] = colour[1]
    image[..., 2] = colour[2]
    image[..., 3] = alpha * 255.0
    return np.clip(image, 0, 255).astype("uint8")


def label_texture(text: str, colour: tuple = (200, 235, 255)) -> np.ndarray:
    """A floating name tag: glowing text on a soft dark pill (RGBA)."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 360, 64
    try:
        font = ImageFont.load_default(size=34)
    except TypeError:
        font = ImageFont.load_default()
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    # Dark translucent pill behind the text.
    pad_x, pad_y = 22, 8
    draw.rounded_rectangle(
        [width // 2 - tw // 2 - pad_x, height // 2 - th // 2 - pad_y,
         width // 2 + tw // 2 + pad_x, height // 2 + th // 2 + pad_y],
        radius=16, fill=(8, 12, 22, 150),
    )
    draw.text((width // 2 - tw // 2 - box[0], height // 2 - th // 2 - box[1]),
              text, font=font, fill=colour + (255,))
    return np.asarray(image).astype("uint8")


def write_game_textures(asset_root: str) -> dict[str, str]:
    """Generate every stylised texture the windowed game uses.

    Written under ``<asset_root>/textures/game/`` and committed, following the
    same convention as the rest of the procedural assets.
    """
    out: dict[str, str] = {}
    tex_dir = os.path.join(asset_root, "textures", "game")
    out["skybox_stars.png"] = write_png(os.path.join(tex_dir, "skybox_stars.png"),
                                       starfield_texture(seed=7))
    out["sun_glow.png"] = write_png(os.path.join(tex_dir, "sun_glow.png"),
                                    glow_sprite(colour=(255, 205, 120), hardness=2.4))
    out["engine_glow.png"] = write_png(os.path.join(tex_dir, "engine_glow.png"),
                                       glow_sprite(size=64, colour=(120, 220, 255), hardness=1.8))
    out["select_ring.png"] = write_png(os.path.join(tex_dir, "select_ring.png"),
                                       _ring_sprite(colour=(110, 235, 255)))
    from src.simulation.bodies import BODIES as _BODIES

    # Labels: the sealed table plus every campaign body the ops layer installs.
    from src.config import CAMPAIGN_BODIES, COMET_KEY
    label_names = {key: body.name for key, body in _BODIES.items()}
    label_names.update({key: spec["name"] for key, spec in CAMPAIGN_BODIES.items()})
    label_names[COMET_KEY] = "Comet Vigil"
    for key, name in label_names.items():
        out[f"label_{key}.png"] = write_png(
            os.path.join(tex_dir, f"label_{key}.png"),
            label_texture(name),
        )
    for key, (base, accent) in GAME_BODY_PALETTES.items():
        if key in GAS_GIANT_TEXTURE_KEYS:
            out[f"{key}.png"] = write_png(
                os.path.join(tex_dir, f"{key}.png"),
                gas_giant_texture(base=base, accent=accent,
                                  seed=12 if key == "boreas" else 5),
            )
            continue
        seed = 900 + zlib.crc32(key.encode("utf-8")) % 5000
        out[f"{key}.png"] = write_png(
            os.path.join(tex_dir, f"{key}.png"),
            planet_texture(256, seed=seed,
                           base=base, accent=accent),
        )
    return out


def _ring_sprite(size: int = 128, colour: tuple = (110, 235, 255)) -> np.ndarray:
    """A thin selection ring with soft edges (RGBA)."""
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - size / 2, yy - size / 2) / (size / 2)
    band = np.exp(-((r - 0.86) ** 2) / (2.0 * 0.03 ** 2))
    image = np.zeros((size, size, 4), dtype=float)
    image[..., 0], image[..., 1], image[..., 2] = colour
    image[..., 3] = band * 255.0
    return np.clip(image, 0, 255).astype("uint8")


# ---------------------------------------------------------------------------
# Procedural audio: everything below synthesises 16-bit mono WAV bytes at
# runtime from numpy, so the game carries no binary sound assets.
# ---------------------------------------------------------------------------

AUDIO_SAMPLE_RATE = 22050


def _write_wav(path: str, samples: "np.ndarray") -> str:
    """Write samples in [-1, 1] as a 16-bit mono WAV; returns the path."""
    import wave

    pcm = np.clip(np.asarray(samples, dtype=float), -1.0, 1.0)
    data = (pcm * 32767.0).astype("<i2").tobytes()
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(AUDIO_SAMPLE_RATE)
        handle.writeframes(data)
    return path


def synth_tone(freq_hz: float, seconds: float, harmonics: tuple = ((1.0, 1.0), (2.0, 0.35), (3.0, 0.12)),
               decay: float = 3.0, sample_rate: int = AUDIO_SAMPLE_RATE) -> "np.ndarray":
    """A decaying harmonic tone; ``decay`` shapes the exponential envelope."""
    t = np.arange(int(seconds * sample_rate), dtype=float) / sample_rate
    wave_form = np.zeros_like(t)
    for multiple, amplitude in harmonics:
        wave_form += amplitude * np.sin(2.0 * math.pi * freq_hz * multiple * t)
    return wave_form * np.exp(-decay * t / max(seconds, 1e-9))


def make_alert_wav(kind: str, path: str) -> str:
    """Alert tones for hull breaches, flares, shortages and good news."""
    rate = AUDIO_SAMPLE_RATE
    if kind == "flare":
        # Rising two-tone: get ready.
        a, b = synth_tone(440.0, 0.22, decay=1.2), synth_tone(660.0, 0.30, decay=1.2)
        samples = np.concatenate([a, b, a, b])
    elif kind == "hull":
        # Low thud, fast decay.
        samples = synth_tone(82.0, 0.5, harmonics=((1.0, 1.0), (2.4, 0.5)), decay=9.0)
    elif kind == "shortage":
        # Uneasy minor pair, slow decay.
        samples = 0.7 * synth_tone(196.0, 0.9, decay=2.0) + 0.7 * synth_tone(233.1, 0.9, decay=2.0)
    elif kind == "contract":
        # Payday chime: two rising notes with a short gap.
        gap = np.zeros(int(0.03 * rate))
        samples = np.concatenate([synth_tone(880.0, 0.2, decay=3.0), gap,
                                  synth_tone(1318.5, 0.4, decay=3.0)])
    else:
        raise ValueError(f"Unknown alert kind '{kind}'.")
    return _write_wav(path, 0.5 * samples / max(1e-9, np.max(np.abs(samples))))


def make_window_chime_wav(path: str) -> str:
    """Bright ascending arpeggio: the launch window just opened - GO."""
    rate = AUDIO_SAMPLE_RATE
    notes = (523.25, 659.25, 783.99, 1046.5)
    gap = int(0.09 * rate)
    parts: list[np.ndarray] = []
    for index, freq in enumerate(notes):
        tone = synth_tone(freq, 0.16, decay=2.2) * (0.5 + 0.12 * index)
        pad = np.zeros(gap)
        parts.append(np.concatenate([tone, pad]) if index < len(notes) - 1 else tone)
    samples = np.concatenate(parts)
    return _write_wav(path, 0.6 * samples / max(1e-9, np.max(np.abs(samples))))


def make_click_wav(path: str) -> str:
    """Tiny UI blip for selections."""
    samples = synth_tone(880.0, 0.05, decay=6.0)
    return _write_wav(path, 0.35 * samples / max(1e-9, np.max(np.abs(samples))))


def make_build_wav(path: str) -> str:
    """Construction thunk-then-chime: a depot comes online."""
    rate = AUDIO_SAMPLE_RATE
    thud = synth_tone(90.0, 0.25, decay=8.0)
    chime = np.zeros(int(0.1 * rate))
    chime = np.concatenate([chime, synth_tone(1046.5, 0.35, decay=3.0)])
    samples = np.concatenate([thud, np.zeros(int(0.05 * rate)), chime])
    return _write_wav(path, 0.6 * samples / max(1e-9, np.max(np.abs(samples))))


def make_hum_wav(path: str, base_hz: float = 55.0, seconds: float = 4.0) -> str:
    """A loopable ambient hum: low fundamental, soft harmonics, slight beat.

    The game pitches the playback rate (hence the hum) with the colony's
    power load, so a busy, hungry colony literally sounds busier.
    """
    rate = AUDIO_SAMPLE_RATE
    t = np.arange(int(seconds * rate), dtype=float) / rate
    samples = (
        0.5 * np.sin(2.0 * math.pi * base_hz * t)
        + 0.2 * np.sin(2.0 * math.pi * base_hz * 2.0 * t + 0.6)
        + 0.12 * np.sin(2.0 * math.pi * base_hz * 3.01 * t)   # slight detune beats
        + 0.05 * np.sin(2.0 * math.pi * base_hz * 0.5 * t)
    )
    # Crossfade the tail into the head so the loop point is seamless.
    fade = min(int(0.05 * rate), len(samples) // 4)
    ramp = np.linspace(0.0, 1.0, fade)
    samples[:fade] = samples[:fade] * ramp + samples[-fade:] * (1.0 - ramp)
    samples = samples[:-fade]
    return _write_wav(path, 0.3 * samples / max(1e-9, np.max(np.abs(samples))))


if __name__ == "__main__":
    # src/utils/procedural.py -> the project root is three levels up, so the
    # assets land in <project>/assets rather than <project>/src/assets.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.join(project_root, "assets")
    for name, path in build_all(root).items():
        print(f"  {name:22s} {os.path.getsize(path) / 1024.0:7.1f} KB  {path}")
