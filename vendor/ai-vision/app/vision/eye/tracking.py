"""Eye tracking module: per-eye analysis from the shared face mesh."""

from __future__ import annotations

import numpy as np

from app.core.types import VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule
from app.vision.eye.geometry import both_eyes

log = get_logger("vision.eye.tracking")


class EyeTrackingModule(VisionModule):
    """Analyses both eyes of the first tracked face per frame.

    Produces per-eye: iris center (px), relative iris position (h/v),
    eye opening (EAR) and tracking state. Reads the face mesh that
    FaceMeshModule already computed — no extra inference.
    """

    key = "eye_tracking"
    display_name = "Eye Tracking"

    def __init__(self, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)

    def load(self) -> None:
        # No model of its own — ready immediately, but only produces data
        # while the face mesh module delivers landmarks.
        self.status_message = ""

    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarks = result.first_raw_mesh()
        if landmarks is None:
            result.eyes = []
            return
        try:
            result.eyes = both_eyes(landmarks)
        except Exception:  # noqa: BLE001 — pipeline isolates module failures
            log.exception("Eye tracking failed on frame")
            result.eyes = []
