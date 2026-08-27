"""Mock image provider — development/offline fallback, clearly labeled.

Generates a simple procedural placeholder image (gradient + "MOCK IMAGE"
label + prompt excerpt + seed). It is *not* a real image generator: the
image is visibly marked MOCK, and every gallery entry records
``is_mock=True``. Used for development and offline smoke tests only.
"""

from __future__ import annotations

import hashlib
from threading import Event
from typing import Callable, Optional

import cv2
import numpy as np

from app.image.providers.base import (
    GeneratedImage,
    ImageCapabilities,
    ImageProvider,
)


class MockImageProvider(ImageProvider):
    """Procedural placeholder generator (clearly marked MOCK).

    Supports the full parameter set (steps/cfg/seed/negative) so the UI
    can be exercised in development; seed changes the placeholder
    deterministically.
    """

    key = "mock"
    display_name = "Mock (dev fallback)"

    @property
    def is_mock(self) -> bool:
        return True

    @property
    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            sizes=(256, 512, 768, 1024),
            steps=True,
            cfg=True,
            seed=True,
            negative_prompt=True,
            models=False,
            progress=True,
            supports_img2img=True,  # dev-mode echo variation (clearly MOCK)
            supports_face_reference=True,  # dev echo (clearly MOCK)
            supports_inpainting=True,      # dev echo (clearly MOCK)
        )

    def availability(self) -> str:
        return "online"

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        model: str = "",
        on_progress: Optional[Callable[[float], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> GeneratedImage:
        width, height = self._width, self._height
        if seed < 0:
            seed = int.from_bytes(hashlib.md5(
                prompt.encode("utf-8")
            ).digest()[:4], "big")
        seed = seed % (2**31)

        # Vertical gradient with a seed-dependent hue.
        y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        hue = (seed % 360) / 360.0
        hsv = np.zeros((height, width, 3), dtype=np.uint8)
        hsv[:, :, 0] = int(hue * 179)
        hsv[:, :, 1] = 120
        hsv[:, :, 2] = (60 + 150 * (1 - y)).astype(np.uint8)
        image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        cv2.putText(
            image, "MOCK IMAGE", (width // 10, height // 3),
            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA,
        )
        cv2.putText(
            image, f"seed {seed} steps {steps} cfg {cfg:.1f}",
            (width // 10, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
        )
        excerpt = (prompt or "")[:52]
        cv2.putText(
            image, f"'{excerpt}'", (width // 10, height // 2 + 36),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA,
        )
        cv2.putText(
            image, "NOT A REAL IMAGE GENERATOR", (width // 10, height - 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA,
        )

        # Simulate progressive work so the queue/progress path is exercised.
        if on_progress is not None:
            for i in range(1, 6):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Generation cancelled.")
                on_progress(i / 5.0)

        ok, png = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("Mock image encoding failed")
        return GeneratedImage(
            png_bytes=png.tobytes(),
            provider=self.key,
            prompt=prompt,
            width=width,
            height=height,
            is_mock=True,
            extra={"seed": seed, "steps": steps, "cfg": cfg,
                   "model": model or "mock-1"},
        )

    def generate_img2img(
        self,
        prompt: str,
        init_image: bytes,
        negative_prompt: str = "",
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        model: str = "",
        on_progress: Optional[Callable[[float], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> GeneratedImage:
        """Dev-mode img2img: echoes the init image with a MOCK banner.

        Clearly labeled — never mistaken for a real variation.
        """
        from app.image.providers.openai_compatible import validate_png

        array = validate_png(init_image)
        resized = cv2.resize(array, (self._width, self._height))
        cv2.putText(
            resized, "MOCK IMG2IMG", (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA,
        )
        ok, png = cv2.imencode(".png", resized)
        if not ok:
            raise RuntimeError("Mock img2img encoding failed")
        return GeneratedImage(
            png_bytes=png.tobytes(),
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            is_mock=True,
            extra={"mode": "img2img", "seed": seed, "steps": steps,
                   "cfg": cfg, "model": model or "mock-1"},
        )

    def inpaint(
        self,
        prompt: str,
        init_image: bytes,
        mask_image: bytes,
        negative_prompt: str = "",
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        model: str = "",
        on_progress: Optional[Callable[[float], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> GeneratedImage:
        """Dev-mode inpaint: echoes the init image with a MOCK banner.

        The mask is validated but not applied (no real model) — the
        result is clearly labeled MOCK INPAINT, never mistaken for a
        real masked regeneration.
        """
        from app.image.providers.openai_compatible import validate_png

        array = validate_png(init_image)
        validate_png(mask_image)
        resized = cv2.resize(array, (self._width, self._height))
        cv2.putText(
            resized, "MOCK INPAINT", (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA,
        )
        ok, png = cv2.imencode(".png", resized)
        if not ok:
            raise RuntimeError("Mock inpaint encoding failed")
        return GeneratedImage(
            png_bytes=png.tobytes(),
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            is_mock=True,
            extra={"mode": "inpaint", "seed": seed, "steps": steps,
                   "cfg": cfg, "model": model or "mock-1"},
        )
