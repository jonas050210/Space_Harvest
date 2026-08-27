"""Person detection/tracking derived from object detections.

The object detector (EfficientDet-Lite0, COCO classes) already recognizes
``person``. This module projects those tracked object boxes into a
dedicated person list — no additional inference runs. The pipeline then
links persons to faces geometrically (face centroid inside the person
box), which yields the Person #n -> Face #m relationship.
"""

from __future__ import annotations

import numpy as np

from app.core.types import TrackedPerson, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule

log = get_logger("vision.persons.tracking")

_PERSON_CLASS = "person"


class PersonTrackingModule(VisionModule):
    """Vision module: persons view over the tracked object detections."""

    key = "person_tracking"
    display_name = "Person Tracking"

    def __init__(self, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)

    def load(self) -> None:
        self.status_message = ""

    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        persons: list[TrackedPerson] = []
        try:
            for obj in result.objects:
                if obj.class_name != _PERSON_CLASS:
                    continue
                persons.append(
                    TrackedPerson(
                        id=obj.id,
                        bbox=obj.bbox,
                        confidence=obj.confidence,
                        tracking_state=obj.tracking_state,
                    )
                )
        except Exception:  # noqa: BLE001 — pipeline isolates failures
            log.exception("Person tracking failed on frame")
            persons = []
        result.persons = persons
