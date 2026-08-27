"""Image generation presets: real prompt/parameter modifications.

Each preset adds a style prefix and suffix, sets sensible default steps
and CFG guidance, and contributes to the negative prompt. Applying a
preset *always* changes the effective prompt — these are not decorative
labels.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Preset registry: name -> (style prefix, style suffix, steps, cfg).
PRESETS: dict[str, tuple[str, str, int, float]] = {
    "REALISTIC": (
        "professional photograph, photorealistic, highly detailed, "
        "natural lighting",
        "",
        30,
        7.0,
    ),
    "CINEMATIC": (
        "cinematic film still, dramatic lighting, shallow depth of field, "
        "35mm",
        "",
        30,
        7.5,
    ),
    "ANIME": (
        "anime style illustration, vibrant colors, clean cel shading",
        "",
        25,
        7.0,
    ),
    "3D": (
        "3D render, octane render, soft studio lighting, highly detailed",
        "",
        30,
        7.0,
    ),
    "SCI-FI": (
        "sci-fi concept art, futuristic technology, glowing accents, "
        "holographic UI",
        "",
        28,
        7.5,
    ),
    "CYBERPUNK": (
        "cyberpunk, neon lights, rainy night city, high contrast",
        "",
        28,
        7.5,
    ),
    "PIXEL ART": (
        "pixel art, 16-bit retro game style, crisp pixels, limited palette",
        "",
        24,
        7.0,
    ),
    "ILLUSTRATION": (
        "digital illustration, clean linework, flat colors",
        "",
        26,
        7.0,
    ),
    "MINIMAL": (
        "minimalist composition, lots of negative space, simple shapes",
        "",
        24,
        7.5,
    ),
    "CONCEPT ART": (
        "concept art, matte painting, epic scale, atmospheric",
        "",
        30,
        7.5,
    ),
    # Phase 9 additions
    "PRODUCT": (
        "professional product photography, studio lighting, seamless "
        "clean background, sharp focus",
        "",
        28,
        7.5,
    ),
    "PORTRAIT": (
        "professional portrait photography, soft key light, shallow "
        "depth of field, 85mm lens",
        "",
        30,
        7.0,
    ),
    "FANTASY": (
        "epic fantasy illustration, magical atmosphere, painterly "
        "detail, dramatic light",
        "",
        30,
        7.5,
    ),
    "ARCHITECTURE": (
        "architectural visualization, clean geometry, ambient "
        "occlusion, realistic materials",
        "",
        30,
        7.5,
    ),
    "GAME ART": (
        "stylized game art, hand-painted textures, bold silhouettes, "
        "vibrant color palette",
        "",
        26,
        7.0,
    ),
}

#: Default negative prompt contributed by most presets (quality baseline).
_DEFAULT_NEGATIVE = (
    "text, watermark, logo, signature, low quality, blurry, deformed"
)


@dataclass
class PresetResult:
    """Effective prompt parameters after applying a preset."""

    prompt: str
    negative_prompt: str
    steps: int
    cfg: float


def apply_preset(
    name: str,
    base_prompt: str,
    negative_prompt: str = "",
    default_steps: int = 20,
    default_cfg: float = 7.0,
) -> PresetResult:
    """Apply a preset to a base prompt; returns effective parameters.

    An unknown/empty preset name leaves the prompt untouched (no fake
    effect). Steps/cfg from the preset override the defaults.
    """
    base = (base_prompt or "").strip()
    negative = (negative_prompt or "").strip()

    if name not in PRESETS:
        return PresetResult(
            prompt=base,
            negative_prompt=negative,
            steps=default_steps,
            cfg=default_cfg,
        )

    prefix, suffix, steps, cfg = PRESETS[name]
    prompt = base
    if prefix:
        prompt = f"{prefix}, {base}" if base else prefix
    if suffix:
        prompt = f"{prompt}, {suffix}"

    negative_parts = [p for p in (negative, _DEFAULT_NEGATIVE) if p]
    return PresetResult(
        prompt=prompt,
        negative_prompt=", ".join(dict.fromkeys(negative_parts)),
        steps=steps,
        cfg=cfg,
    )
