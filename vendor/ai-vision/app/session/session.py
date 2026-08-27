"""In-memory session data (gaze samples + blink events).

Designed for the Phase-3+ heatmap/statistics work:

* Gaze samples are recorded as ``(timestamp, x, y, confidence)`` with x/y
  in normalized video-area coordinates (0..1).
* Blink events are recorded as timestamps.
* Data lives **only in RAM** (bounded deques). Nothing is persisted
  automatically — a later phase can build heatmaps and detailed
  statistics from this structure.
* Thread-safe: the capture worker writes, the UI thread reads.

No camera images are ever stored here.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional

from app.utils.logging_setup import get_logger

log = get_logger("session")

#: One gaze sample: (timestamp, x, y, confidence) — x/y normalized 0..1.
GazeSample = tuple[float, float, float, float]

#: Rolling window for the blink rate (seconds).
_BLINK_RATE_WINDOW = 60.0


class GazeSession:
    """Collects gaze samples and blink events for the current camera session.

    Args:
        max_samples: Maximum gaze samples kept in RAM.
        clock: Injectable monotonic clock (tests).
    """

    def __init__(
        self,
        max_samples: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_samples < 1:
            raise ValueError("max_samples must be >= 1")
        self._clock = clock
        self._lock = threading.Lock()
        self._samples: deque[GazeSample] = deque(maxlen=max_samples)
        self._blinks: deque[float] = deque(maxlen=10_000)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def add_sample(
        self, x: float, y: float, confidence: float, timestamp: Optional[float] = None
    ) -> None:
        """Record one gaze sample (x/y normalized 0..1)."""
        now = self._clock() if timestamp is None else timestamp
        with self._lock:
            self._samples.append((now, float(x), float(y), float(confidence)))

    def add_blink(self, timestamp: Optional[float] = None) -> None:
        """Record one completed blink."""
        now = self._clock() if timestamp is None else timestamp
        with self._lock:
            self._blinks.append(now)
        log.debug("Blink recorded (total: %d)", len(self._blinks))

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def samples(self) -> list[GazeSample]:
        """Copy of the recorded gaze samples (bounded by max_samples)."""
        with self._lock:
            return list(self._samples)

    def recent_trail(self, limit: int, minimum_confidence: float = 0.0) -> list[tuple[float, float]]:
        """Last ``limit`` gaze points above the confidence threshold.

        Used for the gaze trail overlay (x/y normalized 0..1).
        """
        with self._lock:
            points = [
                (x, y)
                for (_, x, y, conf) in self._samples
                if conf >= minimum_confidence
            ]
        return points[-limit:]

    def blink_stats(self, now: Optional[float] = None) -> dict[str, object]:
        """Session blink statistics: count, rate/min, seconds since last."""
        current = self._clock() if now is None else now
        with self._lock:
            count = len(self._blinks)
            window = [t for t in self._blinks if current - t <= _BLINK_RATE_WINDOW]
            rate = len(window) * (60.0 / _BLINK_RATE_WINDOW)
            last = (current - self._blinks[-1]) if self._blinks else None
        return {
            "count": count,
            "rate_per_min": round(rate, 1),
            "last_blink_s": round(last, 2) if last is not None else None,
        }

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def blink_count(self) -> int:
        with self._lock:
            return len(self._blinks)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Clear everything (called when a new camera session starts)."""
        with self._lock:
            self._samples.clear()
            self._blinks.clear()
        log.debug("Session reset")
