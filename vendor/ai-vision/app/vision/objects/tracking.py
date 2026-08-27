"""Object tracking module: raw detections -> ID-stable tracked objects."""

from __future__ import annotations

import numpy as np

from app.core.types import VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule
from app.vision.objects.tracker import ObjectTracker

log = get_logger("vision.objects.tracking")


class ObjectTrackingModule(VisionModule):
    """Assigns stable IDs to the detections of ObjectDetectionModule."""

    key = "object_tracking"
    display_name = "Object Tracking"

    def __init__(
        self,
        enabled: bool = True,
        tracker: ObjectTracker | None = None,
    ) -> None:
        super().__init__(enabled=enabled)
        self._tracker = tracker or ObjectTracker()

    def load(self) -> None:
        self.status_message = ""

    def reset(self) -> None:
        self._tracker.reset()

    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        height, width = frame.shape[:2]
        try:
            result.objects = self._tracker.update(
                result.object_detections, width, height
            )
        except Exception:  # noqa: BLE001 — pipeline isolates module failures
            log.exception("Object tracking failed on frame")
            result.objects = []
