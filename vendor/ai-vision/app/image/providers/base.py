"""Image generation provider interface + capabilities.

Capabilities declare exactly which parameters a provider supports, so the
UI never shows fake sliders: unsupported options are hidden or disabled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Callable, Optional


@dataclass
class ImageCapabilities:
    """Which generation parameters a provider supports."""

    sizes: tuple[int, ...] = (256, 512, 768, 1024)  # allowed square sizes
    steps: bool = False        # sampling steps
    cfg: bool = False          # guidance scale
    seed: bool = False         # deterministic seed
    negative_prompt: bool = False
    models: bool = False       # provider has a model list
    progress: bool = False     # provider reports progress
    # Phase 6
    supports_img2img: bool = False       # image -> image modification
    supports_face_reference: bool = False  # reliable face reference gen
    supports_inpainting: bool = False    # masked inpainting
    # Image *analysis* is app-side (local vision pipeline) and therefore
    # always available — declared here so the UI can gate on it uniformly.
    supports_image_analysis: bool = True

    def supports_size(self, size: int) -> bool:
        return size in self.sizes


@dataclass
class GeneratedImage:
    """Result of one image generation call."""

    png_bytes: bytes
    provider: str
    prompt: str
    width: int
    height: int
    is_mock: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class ImageProvider(ABC):
    """Interface every image backend implements."""

    key: str = ""
    display_name: str = ""
    is_external: bool = False  # True = prompt leaves the machine

    def __init__(self, width: int = 512, height: int = 512,
                 timeout: float = 120.0) -> None:
        self._width = width
        self._height = height
        self._timeout = timeout

    # ------------------------------------------------------------------
    @property
    def is_mock(self) -> bool:
        return False

    @property
    @abstractmethod
    def capabilities(self) -> ImageCapabilities:
        """Supported parameters — the UI renders only these."""

    def availability(self) -> str:
        """online | offline | unavailable | configured — honest status."""
        return "configured"

    def list_models(self) -> list[str]:
        """Models known to this provider (empty when unsupported)."""
        return []

    @abstractmethod
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
        """Generate one image; raises RuntimeError with a readable message.

        ``on_progress`` receives 0..1 if the provider supports progress.
        ``cancel_event`` is cooperative: providers check it between long
        steps; a blocking HTTP call cannot be interrupted mid-flight.
        """

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
        """Image-to-image variation (only for providers with
        ``supports_img2img``). Default: raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Provider '{self.key}' does not support image-to-image."
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
        """Masked regeneration (only for providers with
        ``supports_inpainting``). Default: raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Provider '{self.key}' does not support inpainting."
        )
