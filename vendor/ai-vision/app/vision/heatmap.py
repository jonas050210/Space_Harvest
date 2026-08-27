"""Gaze heatmap (Phase 26) — bounded, RAM-only, thread-safe.

Accumulates gaze samples into a fixed grid (never grows beyond the
grid) and renders them as a translucent RGBA overlay for the live feed
or the Insights page. Purely visual, purely local:

* Samples live in RAM only (mirror of the GazeSession data).
* The grid size is fixed — memory cost is constant regardless of
  session length.
* A simple decay keeps long sessions readable (older samples fade
  toward the background instead of saturating everything).
"""

from __future__ import annotations

import threading
from typing import Sequence

import cv2
import numpy as np

from app.utils.logging_setup import get_logger

log = get_logger("vision.heatmap")

#: Grid resolution (bins) — 64x36 keeps the overlay cost constant.
_GRID_W, _GRID_H = 64, 36

#: Decay factor applied on every decay() call (0..1, 1.0 = no decay).
_DECAY_FACTOR = 0.985

#: Decay is applied at most once per N added samples (cheap amortized).
_DECAY_EVERY = 50

#: Overlay alpha for the rendered heatmap (0..1).
_OVERLAY_ALPHA = 0.45

#: Heatmap colormap (blue -> cyan -> amber -> red), applied via cv2 LUT.
_COLORMAP = np.array(
    [
        [10, 30, 80],     # dark blue
        [120, 160, 30],   # teal
        [40, 200, 220],   # cyan
        [40, 180, 255],   # amber
        [40, 40, 255],    # red
    ],
    dtype=np.uint8,
)


def build_colormap(levels: int = 256) -> np.ndarray:
    """(256, 3) BGR color table interpolated over _COLORMAP.

    Plain numpy indexing is used for the colorization (``table[bin]``)
    — deliberately not cv2.LUT, whose orientation conventions produce
    cryptic OpenCV assertions across versions.
    """
    anchors = _COLORMAP.astype(np.float32)
    positions = np.linspace(0, levels - 1, len(anchors))
    indices = np.arange(levels)
    table = np.zeros((levels, 3), dtype=np.uint8)
    for channel in range(3):
        table[:, channel] = np.interp(
            indices, positions, anchors[:, channel]
        ).astype(np.uint8)
    return table


class GazeHeatmap:
    """Fixed-grid gaze accumulation with an RGBA overlay renderer."""

    def __init__(self, width: int = _GRID_W, height: int = _GRID_H) -> None:
        if width < 4 or height < 4:
            raise ValueError("grid must be at least 4x4")
        self._width = width
        self._height = height
        self._lock = threading.Lock()
        self._grid = np.zeros((height, width), dtype=np.float32)
        self._count = 0
        self._since_decay = 0
        self._max_value = 0.0

    # ------------------------------------------------------------------
    @property
    def sample_count(self) -> int:
        with self._lock:
            return self._count

    def add_points(self, points: Sequence[tuple[float, float, float]]) -> None:
        """Accumulate (x, y, confidence) samples; x/y normalized 0..1.

        Out-of-range or non-finite values are ignored (never crash the
        capture loop on bad gaze data).
        """
        if not points:
            return
        with self._lock:
            for point in points:
                x, y, confidence = point
                if not (np.isfinite(x) and np.isfinite(y)):
                    continue
                bx = int(np.clip(x, 0.0, 0.999999) * self._width)
                by = int(np.clip(y, 0.0, 0.999999) * self._height)
                weight = float(np.clip(confidence, 0.0, 1.0))
                self._grid[by, bx] += 0.5 + weight
                self._count += 1
                self._since_decay += 1
            if self._since_decay >= _DECAY_EVERY:
                self._grid *= _DECAY_FACTOR
                self._since_decay = 0
            self._max_value = max(self._max_value, float(self._grid.max()))

    # ------------------------------------------------------------------
    def overlay(self, width: int, height: int) -> np.ndarray:
        """Render the heatmap as an RGBA overlay (BGR + alpha channel).

        Returns a ``(height, width, 4)`` uint8 array; alpha is zero
        where no gaze was recorded. Cheap and cacheable — the caller
        decides how often to call this.
        """
        with self._lock:
            grid = self._grid.copy()
            maximum = self._max_value
        if maximum <= 0.0:
            return np.zeros((height, width, 4), dtype=np.uint8)

        normalized = np.clip(grid / maximum, 0.0, 1.0)
        indices = (normalized * 255).astype(np.uint8)
        table = build_colormap()
        small = table[indices].reshape(self._height, self._width, 3)
        resized = cv2.resize(
            small, (width, height), interpolation=cv2.INTER_LINEAR
        )
        alpha = (
            normalized > 0.01
        ).astype(np.float32)
        alpha = cv2.resize(alpha, (width, height),
                           interpolation=cv2.INTER_LINEAR)
        alpha = (alpha * _OVERLAY_ALPHA * 255.0).astype(np.uint8)
        overlay = np.dstack([resized, alpha])
        return overlay

    def coverage(self) -> float:
        """Fraction of grid bins that ever received gaze (0..1)."""
        with self._lock:
            if self._count == 0:
                return 0.0
            return round(
                float((self._grid > 0.0).mean()), 4
            )

    def clear(self) -> None:
        with self._lock:
            self._grid.fill(0.0)
            self._count = 0
            self._since_decay = 0
            self._max_value = 0.0
