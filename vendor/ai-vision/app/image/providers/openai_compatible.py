"""OpenAI-compatible image generation provider (Images API shape).

Works with the OpenAI Images API and local servers exposing the same
shape. Two scopes share the implementation:

* ``LocalImageProvider`` — an OpenAI-compatible endpoint on the local
  network: prompts stay on your machine.
* ``APIImageProvider`` — a remote third-party endpoint: prompts leave the
  machine. The UI labels this clearly as EXTERNAL PROVIDER and only sends
  prompts on an explicit user action (pressing GENERATE).

API key: read from the ``AI_VISION_LAB_API_KEY`` environment variable —
never from settings, source code or logs. The returned image data is
validated (PNG decode) — corrupt responses raise a readable error.
"""

from __future__ import annotations

import base64
import os
from threading import Event
from typing import Callable, Optional

import cv2
import numpy as np

from app.ai.providers.http import http_get_bytes, http_post_json
from app.image.providers.base import (
    GeneratedImage,
    ImageCapabilities,
    ImageProvider,
)
from app.utils.logging_setup import get_logger

log = get_logger("image.providers.openai")

API_KEY_ENV = "AI_VISION_LAB_API_KEY"
DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"


def validate_png(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes; raises RuntimeError on corrupt image data."""
    if not png_bytes or len(png_bytes) < 8:
        raise RuntimeError("Image provider returned empty image data.")
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Image provider returned non-PNG image data.")
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Image provider returned corrupt image data.")
    return image


class OpenAICompatibleImageProvider(ImageProvider):
    """Images API backend (local or remote scope).

    Parameter support mirrors the OpenAI Images API: no steps/cfg/seed
    and no negative prompt — the UI hides these options.
    """

    key = "openai_compatible_image"
    display_name = "OpenAI-compatible images"
    is_external = True

    def __init__(
        self,
        base_url: str,
        model: str = "",
        width: int = 512,
        height: int = 512,
        timeout: float = 120.0,
        api_key: Optional[str] = None,
        scope: str = "external",
    ) -> None:
        super().__init__(width=width, height=height, timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = (
            api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        )
        self._scope = scope  # "local" | "external"

    # ------------------------------------------------------------------
    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    @property
    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            sizes=(256, 512, 768, 1024),
            steps=False,
            cfg=False,
            seed=False,
            negative_prompt=False,
            models=True,
            progress=False,
        )

    def list_models(self) -> list[str]:
        # The Images API has no model list endpoint; the model stays a
        # free-text field (e.g. "gpt-image-1", "dall-e-3").
        return [self._model] if self._model else []

    def availability(self) -> str:
        if not self._api_key:
            return "unavailable"  # no key -> cannot work
        return "configured"

    # ------------------------------------------------------------------
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
        if not self._api_key:
            raise RuntimeError(
                f"No API key configured. Set the {API_KEY_ENV} "
                "environment variable."
            )
        payload = {
            "prompt": prompt,
            "n": 1,
            "size": f"{self._width}x{self._height}",
            "response_format": "b64_json",
        }
        if model or self._model:
            payload["model"] = model or self._model
        try:
            _status, data = http_post_json(
                f"{self._base_url}/images/generations",
                payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"Image generation failed: {exc}") from exc

        png_bytes = _extract_image_bytes(data, timeout=self._timeout)
        if not png_bytes:
            raise RuntimeError("Image API response contained no image data.")
        validate_png(png_bytes)  # corrupt data -> readable error
        return GeneratedImage(
            png_bytes=png_bytes,
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            extra={"scope": self._scope, "model": model or self._model},
        )


def _extract_image_bytes(data: dict, timeout: float) -> Optional[bytes]:
    """b64_json first, then url download — the two common response shapes."""
    items = data.get("data") or []
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict) and first.get("b64_json"):
        try:
            return base64.b64decode(first["b64_json"])
        except (ValueError, TypeError):
            return None
    if isinstance(first, dict) and first.get("url"):
        try:
            return http_get_bytes(first["url"], timeout=timeout)
        except RuntimeError as exc:
            raise RuntimeError(f"Could not download generated image: {exc}") from exc
    return None


class LocalImageProvider(OpenAICompatibleImageProvider):
    """OpenAI-compatible endpoint on the local machine / network."""

    key = "local"
    display_name = "Local endpoint (OpenAI-compatible)"
    is_external = False

    def __init__(self, base_url: str = DEFAULT_LOCAL_BASE_URL, **kwargs) -> None:
        super().__init__(base_url=base_url, scope="local", **kwargs)


class APIImageProvider(OpenAICompatibleImageProvider):
    """Remote third-party image API — prompts leave the machine."""

    key = "external"
    display_name = "External API (prompt leaves this machine)"
    is_external = True

    def __init__(self, base_url: str, **kwargs) -> None:
        super().__init__(base_url=base_url, scope="external", **kwargs)
