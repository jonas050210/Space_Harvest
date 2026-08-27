"""Stable Diffusion WebUI provider — AUTOMATIC1111 / Forge / SD.Next.

Local Stable Diffusion via the well-known HTTP API:

* ``POST /sdapi/v1/txt2img`` — text-to-image (base64 PNGs in the reply)
* ``GET  /sdapi/v1/sd-models`` — installed checkpoints (model picker)
* ``GET  /sdapi/v1/progress`` — live progress (polled while generating)

Fully local (prompts never leave the machine), supports the full
parameter set: negative prompt, steps, CFG, seed, size, model. The seed
actually used is read back from the response ``info`` block so the
gallery metadata is honest even with ``seed = -1`` (random). Timeout and
cancel are handled cooperatively; corrupt image data is rejected with a
readable error.
"""

from __future__ import annotations

import base64
import json
import threading
from threading import Event
from typing import Callable, Optional

from app.ai.providers.http import http_get_json, http_post_json
from app.image.providers.base import (
    GeneratedImage,
    ImageCapabilities,
    ImageProvider,
)
from app.image.providers.openai_compatible import validate_png
from app.utils.logging_setup import get_logger

log = get_logger("image.providers.sdwebui")

DEFAULT_BASE_URL = "http://127.0.0.1:7860"


class SDWebUIProvider(ImageProvider):
    """Stable Diffusion WebUI backend (AUTOMATIC1111-compatible API)."""

    key = "sdwebui"
    display_name = "Stable Diffusion WebUI (local)"
    is_external = False

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        width: int = 512,
        height: int = 512,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(width=width, height=height, timeout=timeout)
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    @property
    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            sizes=(256, 512, 768, 1024),
            steps=True,
            cfg=True,
            seed=True,
            negative_prompt=True,
            models=True,
            progress=True,
            supports_img2img=True,
            # Face reference: the locally stored face photo is used as
            # the img2img init image (real local conditioning — the
            # photo never leaves the machine).
            supports_face_reference=True,
            supports_inpainting=True,
        )

    def availability(self) -> str:
        try:
            http_get_json(f"{self._base_url}/sdapi/v1/sd-models", timeout=2.0)
            return "online"
        except RuntimeError:
            return "offline"

    def list_models(self) -> list[str]:
        try:
            _status, data = http_get_json(
                f"{self._base_url}/sdapi/v1/sd-models", timeout=3.0
            )
        except RuntimeError as exc:
            log.debug("SD WebUI model list failed: %s", exc)
            return []
        models = data if isinstance(data, list) else []
        titles = [
            entry.get("title")
            for entry in models
            if isinstance(entry, dict) and entry.get("title")
        ]
        return titles

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
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": int(steps),
            "cfg_scale": float(cfg),
            "width": self._width,
            "height": self._height,
            "seed": int(seed),
            "batch_size": 1,
        }
        if model:
            # Override the currently loaded checkpoint (works with
            # AUTOMATIC1111/Forge; ignored gracefully by SD.Next).
            payload["override_settings"] = {"sd_model_checkpoint": model}

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Generation cancelled.")

        if on_progress is not None:
            stop_polling = threading.Event()
            poller = threading.Thread(
                target=self._progress_poller,
                args=(on_progress, stop_polling, cancel_event),
                daemon=True,
            )
            poller.start()
        else:
            poller = None

        try:
            _status, data = http_post_json(
                f"{self._base_url}/sdapi/v1/txt2img",
                payload,
                timeout=self._timeout,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"Stable Diffusion WebUI is not reachable at "
                f"{self._base_url}: {exc}"
            ) from exc
        finally:
            if poller is not None:
                stop_polling.set()
                poller.join(timeout=2)

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Generation cancelled.")

        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise RuntimeError(
                "Stable Diffusion WebUI response contained no image."
            )
        try:
            png_bytes = base64.b64decode(images[0])
        except (ValueError, TypeError, IndexError) as exc:
            raise RuntimeError(
                "Stable Diffusion WebUI returned invalid image data."
            ) from exc
        validate_png(png_bytes)

        used_seed = _extract_seed(data)
        return GeneratedImage(
            png_bytes=png_bytes,
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            extra={
                "model": model,
                "seed": used_seed,
                "steps": int(steps),
                "cfg": float(cfg),
                "negative_prompt": negative_prompt,
                "scope": "local",
            },
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
        """Masked regeneration via the A1111 img2img API.

        ``init_image`` and ``mask_image`` are validated PNGs; the mask
        is uploaded base64 (white = regenerate, black = keep).
        """
        validate_png(init_image)
        validate_png(mask_image)
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": int(steps),
            "cfg_scale": float(cfg),
            "width": self._width,
            "height": self._height,
            "seed": int(seed),
            "denoising_strength": 0.75,
            "batch_size": 1,
            "init_images": [base64.b64encode(init_image).decode("ascii")],
            "mask": base64.b64encode(mask_image).decode("ascii"),
        }
        if model:
            payload["override_settings"] = {"sd_model_checkpoint": model}
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Generation cancelled.")
        try:
            _status, data = http_post_json(
                f"{self._base_url}/sdapi/v1/img2img",
                payload,
                timeout=self._timeout,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"Stable Diffusion WebUI inpaint failed: {exc}"
            ) from exc
        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise RuntimeError(
                "Stable Diffusion WebUI inpaint response contained "
                "no image."
            )
        try:
            png_bytes = base64.b64decode(images[0])
        except (ValueError, TypeError, IndexError) as exc:
            raise RuntimeError(
                "Stable Diffusion WebUI returned invalid image data."
            ) from exc
        validate_png(png_bytes)
        return GeneratedImage(
            png_bytes=png_bytes,
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            extra={
                "model": model,
                "seed": _extract_seed(data),
                "steps": int(steps),
                "cfg": float(cfg),
                "negative_prompt": negative_prompt,
                "scope": "local",
                "mode": "inpaint",
            },
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
        """Image-to-image via POST /sdapi/v1/img2img (AUTOMATIC1111 API).

        ``init_image`` (PNG bytes) is validated before upload; the
        resulting image is validated after decoding.
        """
        validate_png(init_image)  # corrupt input -> readable error
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": int(steps),
            "cfg_scale": float(cfg),
            "width": self._width,
            "height": self._height,
            "seed": int(seed),
            "denoising_strength": 0.55,
            "batch_size": 1,
            "init_images": [base64.b64encode(init_image).decode("ascii")],
        }
        if model:
            payload["override_settings"] = {"sd_model_checkpoint": model}

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Generation cancelled.")

        try:
            _status, data = http_post_json(
                f"{self._base_url}/sdapi/v1/img2img",
                payload,
                timeout=self._timeout,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"Stable Diffusion WebUI img2img failed: {exc}"
            ) from exc

        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise RuntimeError(
                "Stable Diffusion WebUI img2img response contained no image."
            )
        try:
            png_bytes = base64.b64decode(images[0])
        except (ValueError, TypeError, IndexError) as exc:
            raise RuntimeError(
                "Stable Diffusion WebUI returned invalid image data."
            ) from exc
        validate_png(png_bytes)
        return GeneratedImage(
            png_bytes=png_bytes,
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            extra={
                "model": model,
                "seed": _extract_seed(data),
                "steps": int(steps),
                "cfg": float(cfg),
                "negative_prompt": negative_prompt,
                "scope": "local",
                "mode": "img2img",
            },
        )

    # ------------------------------------------------------------------
    def _progress_poller(
        self,
        on_progress: Callable[[float], None],
        stop: threading.Event,
        cancel_event: Optional[Event],
    ) -> None:
        """Poll GET /sdapi/v1/progress while the txt2img POST runs."""
        last = -1.0
        while not stop.is_set():
            try:
                _status, data = http_get_json(
                    f"{self._base_url}/sdapi/v1/progress", timeout=1.0
                )
                progress = float(data.get("progress", 0.0) or 0.0)
                if 0.0 <= progress <= 1.0 and abs(progress - last) > 0.01:
                    last = progress
                    on_progress(progress)
            except (RuntimeError, TypeError, ValueError):
                pass  # progress polling is best-effort
            stop.wait(0.4)
        if last < 1.0 and not (
            cancel_event is not None and cancel_event.is_set()
        ):
            try:
                on_progress(1.0)
            except Exception:  # noqa: BLE001 — callback may be gone
                pass


def _extract_seed(data: dict) -> Optional[int]:
    """Read the seed actually used from the response ``info`` block."""
    info = data.get("info")
    if not isinstance(info, str):
        return None
    try:
        parsed = json.loads(info)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return int(parsed.get("seed", -1))
    except (TypeError, ValueError):
        return None
