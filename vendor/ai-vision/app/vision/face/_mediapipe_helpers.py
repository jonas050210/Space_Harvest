"""Shared MediaPipe runtime helpers for the face modules.

All MediaPipe imports are lazy (inside functions), so the application and
the whole ``app.vision`` package remain importable — and the GUI usable —
even when mediapipe is not installed. The modules report a clean
:class:`ModelLoadError` in that case.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from app.utils.logging_setup import get_logger


def make_mp_image(frame_bgr: np.ndarray):
    """Convert a BGR OpenCV frame into a MediaPipe SRGB image."""
    from app.utils.protobuf_compat import apply_protobuf_compat

    apply_protobuf_compat()
    import mediapipe as mp  # noqa: PLC0415 — lazy import

    rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def box_to_pixels(
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int]:
    """Convert a MediaPipe bounding box to pixel coordinates.

    MediaPipe releases differ here: some return normalized boxes (all
    values <= 1.0, as documented), newer versions return boxes already in
    pixels of the input image. Both regimes are handled: normalized values
    are scaled, pixel values are used directly (clamped to the frame).
    """
    if max(origin_x, origin_y, width, height) <= 1.0:
        x = int(round(origin_x * frame_w))
        y = int(round(origin_y * frame_h))
        w = max(1, int(round(width * frame_w)))
        h = max(1, int(round(height * frame_h)))
    else:
        x, y = int(round(origin_x)), int(round(origin_y))
        w, h = max(1, int(round(width))), max(1, int(round(height)))
    x = max(0, min(x, frame_w - 1))
    y = max(0, min(y, frame_h - 1))
    w = max(1, min(w, frame_w - x))
    h = max(1, min(h, frame_h - y))
    return x, y, w, h


class MonotonicTimestamps:
    """Strictly increasing millisecond timestamps for VIDEO-mode tasks."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._last: Optional[int] = None

    def next(self) -> int:
        value = int(self._clock() * 1000)
        if self._last is not None and value <= self._last:
            value = self._last + 1
        self._last = value
        return value


def create_task_with_fallback(
    build_options,
    create_fn,
    model_path,
    use_gpu: bool,
    module_name: str,
):
    """Create a MediaPipe task; GPU delegate with automatic CPU fallback.

    MediaPipe's GPU delegate depends on the platform build (on Windows it
    is frequently unavailable for the Tasks API). Stability beats GPU
    usage: if GPU creation fails, the task is retried on the CPU delegate
    and the fallback is logged — the module keeps working either way.

    Args:
        build_options: ``fn(BaseOptions) -> Options`` for the task type.
        create_fn: ``Task.create_from_options`` bound method.
        model_path: Model file path.
        use_gpu: Whether a GPU delegate was requested.
        module_name: Logging label.

    Returns: (task, delegate_used: str) — delegate is "gpu" or "cpu".
    """
    from app.utils.protobuf_compat import apply_protobuf_compat

    apply_protobuf_compat()
    from mediapipe.tasks import python as mp_python  # noqa: PLC0415 — lazy

    if use_gpu:
        try:
            base = mp_python.BaseOptions(
                model_asset_path=str(model_path),
                delegate=mp_python.BaseOptions.Delegate.GPU,
            )
            task = create_fn(build_options(base))
            get_logger(f"vision.{module_name}").info(
                "%s: GPU delegate active", module_name
            )
            return task, "gpu"
        except Exception as exc:  # noqa: BLE001 — platform-dependent
            get_logger(f"vision.{module_name}").warning(
                "%s: GPU delegate unavailable (%s) — falling back to CPU",
                module_name, exc,
            )

    base = mp_python.BaseOptions(model_asset_path=str(model_path))
    task = create_fn(build_options(base))
    return task, "cpu"

