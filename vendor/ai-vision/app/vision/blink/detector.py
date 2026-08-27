"""Blink detection from shared face-mesh landmarks.

EAR (Eye Aspect Ratio) is computed per eye from the canonical six-point
sets. A state machine (OPEN -> CLOSING -> CLOSED -> OPENING -> OPEN) with
temporal debounce decides when a real blink happened:

* CLOSED must persist for several consecutive frames (a single bad frame
  is ignored).
* The blink duration must lie inside a plausible range (0.05..0.8 s).
* A minimum interval between counted blinks avoids double counting.

Blink events are recorded in the :class:`GazeSession`; statistics
(count, rate/min, last blink) are computed from real session data.
"""

from __future__ import annotations

import enum
import time
from typing import Callable, Optional

import numpy as np

from app.core.types import BlinkFrameInfo, VisionResult
from app.session.session import GazeSession
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule
from app.vision.eye.geometry import ear

log = get_logger("vision.blink.detector")


class BlinkState(enum.Enum):
    WAITING = "WAITING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    OPENING = "OPENING"


class BlinkDetectorModule(VisionModule):
    """EAR-based blink detector with temporal debouncing."""

    key = "blink_detection"
    display_name = "Blink Detection"

    def __init__(
        self,
        session: GazeSession,
        enabled: bool = True,
        open_threshold: float = 0.20,
        closed_threshold: float = 0.13,
        reopening_threshold: float = 0.18,
        min_closed_frames: int = 2,
        min_blink_seconds: float = 0.05,
        max_blink_seconds: float = 0.8,
        min_interval_seconds: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(enabled=enabled)
        if not 0.0 < closed_threshold < reopening_threshold < open_threshold:
            raise ValueError(
                "Requires 0 < closed < reopening < open thresholds"
            )
        self._session = session
        self._open_threshold = open_threshold
        self._closed_threshold = closed_threshold
        self._reopening_threshold = reopening_threshold
        self._min_closed_frames = min_closed_frames
        self._min_blink_seconds = min_blink_seconds
        self._max_blink_seconds = max_blink_seconds
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock

        self._state = BlinkState.WAITING
        self._closed_frames = 0
        self._closed_since: Optional[float] = None
        self._last_blink_at: Optional[float] = None

    # ------------------------------------------------------------------
    def load(self) -> None:
        self.status_message = ""

    def reset(self) -> None:
        """Forget the state machine (new camera session)."""
        self._state = BlinkState.WAITING
        self._closed_frames = 0
        self._closed_since = None
        self._last_blink_at = None

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarks = result.first_raw_mesh()
        if landmarks is None:
            self._state = BlinkState.WAITING
            result.blink = self._frame_info(ear_value=None)
            return

        try:
            ear_left = ear(landmarks, "left")
            ear_right = ear(landmarks, "right")
        except Exception:  # noqa: BLE001 — bad landmarks
            ear_left = ear_right = None

        values = [v for v in (ear_left, ear_right) if v is not None]
        if not values:
            self._state = BlinkState.WAITING
            result.blink = self._frame_info(ear_value=None, ear_l=ear_left, ear_r=ear_right)
            return

        ear_value = float(np.mean(values))
        event = self._update(ear_value)
        result.blink = self._frame_info(ear_value, ear_l=ear_left, ear_r=ear_right)
        result.blink.blink_event = event
        if event:
            self._session.add_blink()

    # ------------------------------------------------------------------
    def _update(self, ear_value: float) -> bool:
        """Advance the state machine; returns True if a blink completed."""
        now = self._clock()
        event = False

        if self._state in (BlinkState.WAITING, BlinkState.OPEN):
            if ear_value < self._closed_threshold:
                self._state = BlinkState.CLOSING
            else:
                self._state = BlinkState.OPEN

        elif self._state is BlinkState.CLOSING:
            if ear_value < self._closed_threshold:
                self._state = BlinkState.CLOSED
                self._closed_frames = 1
                self._closed_since = now
            elif ear_value >= self._reopening_threshold:
                self._state = BlinkState.OPEN  # false start

        elif self._state is BlinkState.CLOSED:
            if ear_value < self._closed_threshold:
                self._closed_frames += 1
            else:
                # Confirmed only after the debounce window.
                if self._closed_frames >= self._min_closed_frames:
                    duration = (
                        (now - self._closed_since)
                        if self._closed_since is not None
                        else 0.0
                    )
                    interval = (
                        (now - self._last_blink_at)
                        if self._last_blink_at is not None
                        else float("inf")
                    )
                    if (
                        self._min_blink_seconds <= duration <= self._max_blink_seconds
                        and interval >= self._min_interval_seconds
                    ):
                        self._last_blink_at = now
                        event = True
                        log.debug("Blink counted (duration %.2f s)", duration)
                self._state = BlinkState.OPENING

        elif self._state is BlinkState.OPENING:
            if ear_value >= self._open_threshold:
                self._state = BlinkState.OPEN
            elif ear_value < self._closed_threshold:
                self._state = BlinkState.CLOSING

        return event

    # ------------------------------------------------------------------
    def _frame_info(
        self,
        ear_value: Optional[float],
        ear_l: Optional[float] = None,
        ear_r: Optional[float] = None,
    ) -> BlinkFrameInfo:
        stats = self._session.blink_stats()
        return BlinkFrameInfo(
            state=self._state.value,
            ear=None if ear_value is None else round(ear_value, 4),
            ear_left=None if ear_l is None else round(ear_l, 4),
            ear_right=None if ear_r is None else round(ear_r, 4),
            count=int(stats["count"]),
            rate_per_min=float(stats["rate_per_min"]),
            last_blink_s=stats["last_blink_s"],
        )

    @property
    def state(self) -> BlinkState:
        return self._state
