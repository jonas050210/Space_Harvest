"""FPS / frame-time measurement.

A lightweight sliding-window meter: one ``tick()`` per processed frame.
Reading the stats is O(window) and cheap enough to run at UI refresh rate,
but the UI polls it at most ~30 Hz and never inside the capture loop.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional

from app.core.types import FpsStats


class FPSMeter:
    """Measures fps and frame time over a sliding time window.

    Args:
        window_seconds: Length of the sliding measurement window.
        clock: Injectable monotonic clock (tests pass a fake clock).
    """

    def __init__(
        self,
        window_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window = float(window_seconds)
        self._clock = clock
        self._timestamps: deque[float] = deque()
        self._ema_frame_time: Optional[float] = None
        self._total_frames = 0

    def tick(self) -> None:
        """Record one processed frame."""
        now = self._clock()
        if self._timestamps:
            interval = now - self._timestamps[-1]
            if interval > 0:
                alpha = 0.15
                if self._ema_frame_time is None:
                    self._ema_frame_time = interval
                else:
                    self._ema_frame_time = (
                        alpha * interval + (1.0 - alpha) * self._ema_frame_time
                    )
        self._timestamps.append(now)
        self._total_frames += 1
        self._prune(now)

    def reset(self) -> None:
        """Clear all measurements."""
        self._timestamps.clear()
        self._ema_frame_time = None
        self._total_frames = 0

    @property
    def stats(self) -> FpsStats:
        """Current measurements without mutating state."""
        now = self._clock()
        if self._timestamps:
            self._prune(now)
        span = (
            self._timestamps[-1] - self._timestamps[0]
            if len(self._timestamps) >= 2
            else 0.0
        )
        fps = (len(self._timestamps) - 1) / span if span > 0 else 0.0
        frame_time_ms = (
            self._ema_frame_time * 1000.0 if self._ema_frame_time is not None else 0.0
        )
        return FpsStats(
            fps=round(fps, 1),
            frame_time_ms=round(frame_time_ms, 1),
            total_frames=self._total_frames,
        )

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
