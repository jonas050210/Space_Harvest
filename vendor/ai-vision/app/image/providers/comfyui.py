"""ComfyUI image provider — local graph API (Phase 28).

Talks to a running ComfyUI instance (default ``http://127.0.0.1:8188``)
using the documented HTTP protocol:

* ``GET  /system_stats``     — availability
* ``GET  /object_info``      — checkpoint list
* ``POST /prompt``           — queue a workflow
* ``GET  /history/{id}``     — wait for the result
* ``GET  /view``             — fetch the PNG

Fully local: the prompt never leaves the machine. If ComfyUI is not
running the provider reports OFFLINE — never a fake image. A missing
checkpoint is a readable error, not a hang.
"""

from __future__ import annotations

import time
import uuid
from threading import Event
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from app.ai.providers.http import http_get_bytes, http_get_json, http_post_json
from app.image.providers.base import (
    GeneratedImage,
    ImageCapabilities,
    ImageProvider,
)
from app.image.providers.openai_compatible import validate_png
from app.utils.logging_setup import get_logger

log = get_logger("image.providers.comfyui")

DEFAULT_BASE_URL = "http://127.0.0.1:8188"
_POLL_INTERVAL = 0.4


class ComfyUIProvider(ImageProvider):
    """Local ComfyUI backend (txt2img via a built-in SD1.5-style graph)."""

    key = "comfyui"
    display_name = "ComfyUI (local)"
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
        self._client_id = f"ai-vision-lab-{uuid.uuid4().hex[:8]}"

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
            supports_img2img=False,
            supports_face_reference=False,
            supports_inpainting=False,
        )

    def availability(self) -> str:
        try:
            http_get_json(f"{self._base_url}/system_stats", timeout=2.0)
            return "online"
        except RuntimeError:
            return "offline"

    def list_models(self) -> list[str]:
        try:
            _status, data = http_get_json(
                f"{self._base_url}/object_info", timeout=4.0
            )
        except RuntimeError as exc:
            log.debug("ComfyUI object_info failed: %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        loader = data.get("CheckpointLoaderSimple") or {}
        inputs = (
            loader.get("input", {}).get("required", {})
            if isinstance(loader, dict) else {}
        )
        ckpt = inputs.get("ckpt_name") if isinstance(inputs, dict) else None
        # ComfyUI encodes combo boxes as [ [name, …], {…} ].
        if isinstance(ckpt, list) and ckpt and isinstance(ckpt[0], list):
            return [str(name) for name in ckpt[0] if name]
        return []

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
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Generation cancelled.")
        ckpt = model.strip()
        if not ckpt:
            models = self.list_models()
            if not models:
                raise RuntimeError(
                    f"ComfyUI at {self._base_url} has no checkpoint "
                    "loaded — drop a .safetensors file into ComfyUI's "
                    "models/checkpoints folder."
                )
            ckpt = models[0]
        used_seed = int(seed) if int(seed) >= 0 else int(uuid.uuid4().int % 2_147_483_647)
        workflow = _txt2img_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            steps=int(steps),
            cfg=float(cfg),
            seed=used_seed,
            width=self._width,
            height=self._height,
            ckpt_name=ckpt,
        )
        try:
            _status, queued = http_post_json(
                f"{self._base_url}/prompt",
                {"prompt": workflow, "client_id": self._client_id},
                timeout=15.0,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"ComfyUI is not reachable at {self._base_url}: {exc}"
            ) from exc
        if not isinstance(queued, dict) or not queued.get("prompt_id"):
            error = queued.get("error") if isinstance(queued, dict) else queued
            raise RuntimeError(f"ComfyUI rejected the workflow: {error}")
        prompt_id = str(queued["prompt_id"])
        png_bytes = self._wait_for_image(
            prompt_id, on_progress=on_progress, cancel_event=cancel_event
        )
        validate_png(png_bytes)
        if on_progress is not None:
            try:
                on_progress(1.0)
            except Exception:  # noqa: BLE001
                pass
        return GeneratedImage(
            png_bytes=png_bytes,
            provider=self.key,
            prompt=prompt,
            width=self._width,
            height=self._height,
            extra={
                "model": ckpt,
                "seed": used_seed,
                "steps": int(steps),
                "cfg": float(cfg),
                "negative_prompt": negative_prompt,
                "scope": "local",
                "prompt_id": prompt_id,
            },
        )

    # ------------------------------------------------------------------
    def _wait_for_image(
        self,
        prompt_id: str,
        on_progress: Optional[Callable[[float], None]],
        cancel_event: Optional[Event],
    ) -> bytes:
        deadline = time.monotonic() + self._timeout
        last_progress = -1.0
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Generation cancelled.")
            try:
                _status, history = http_get_json(
                    f"{self._base_url}/history/{prompt_id}", timeout=4.0
                )
            except RuntimeError:
                time.sleep(_POLL_INTERVAL)
                continue
            entry = _history_entry(history, prompt_id)
            if entry is not None:
                status_str = str(
                    (entry.get("status") or {}).get("status_str", "")
                ).lower()
                if status_str == "error" or entry.get("status", {}).get(
                    "completed"
                ) is False and status_str:
                    messages = (entry.get("status") or {}).get("messages") or []
                    raise RuntimeError(
                        f"ComfyUI workflow failed: {messages[:1] or status_str}"
                    )
                images = _output_images(entry)
                if images:
                    return self._fetch_view(images[0])
            if on_progress is not None:
                # Honest: ComfyUI history has no 0..1 progress. We report
                # a slow ramp that never claims 100 % until the image lands.
                elapsed = self._timeout - max(0.0, deadline - time.monotonic())
                progress = min(0.9, elapsed / max(self._timeout, 1.0))
                if abs(progress - last_progress) > 0.05:
                    last_progress = progress
                    try:
                        on_progress(progress)
                    except Exception:  # noqa: BLE001
                        pass
            time.sleep(_POLL_INTERVAL)
        raise RuntimeError(
            f"ComfyUI timed out after {self._timeout:.0f}s waiting for "
            f"prompt {prompt_id}."
        )

    def _fetch_view(self, image: dict[str, Any]) -> bytes:
        query = urlencode(
            {
                "filename": image.get("filename", ""),
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        return http_get_bytes(f"{self._base_url}/view?{query}", timeout=30.0)


def _history_entry(history: Any, prompt_id: str) -> Optional[dict]:
    if not isinstance(history, dict):
        return None
    # /history/{id} sometimes wraps {id: entry}, sometimes is the entry.
    if prompt_id in history and isinstance(history[prompt_id], dict):
        return history[prompt_id]
    if "outputs" in history:
        return history
    return None


def _output_images(entry: dict) -> list[dict]:
    outputs = entry.get("outputs") or {}
    if not isinstance(outputs, dict):
        return []
    images: list[dict] = []
    for node in outputs.values():
        if not isinstance(node, dict):
            continue
        for item in node.get("images") or []:
            if isinstance(item, dict) and item.get("filename"):
                images.append(item)
    return images


def _txt2img_workflow(
    prompt: str,
    negative_prompt: str,
    steps: int,
    cfg: float,
    seed: int,
    width: int,
    height: int,
    ckpt_name: str,
) -> dict[str, Any]:
    """Minimal SD1.5-style graph using only built-in ComfyUI nodes."""
    return {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt_name},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(seed),
                "steps": max(1, int(steps)),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "AIVisionLab",
                "images": ["8", 0],
            },
        },
    }
