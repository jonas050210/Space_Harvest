"""Face detection module (MediaPipe BlazeFace short-range model).

Produces bounding boxes with confidence for every detected face. Face IDs
are *not* assigned here — the pipeline's FaceTracker turns the raw boxes
into ID-stable faces across frames.
"""

from __future__ import annotations

import numpy as np

from app.core.errors import ModelLoadError, VisionError
from app.core.types import FaceBox, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.face._mediapipe_helpers import (
    MonotonicTimestamps,
    box_to_pixels,
    create_task_with_fallback,
    make_mp_image,
)
from app.vision.model_manager import ModelManager

log = get_logger("vision.face.detection")


class FaceDetectionModule(VisionModule):
    """BlazeFace short-range face detector with confidence scores.

    Args:
        models_dir: Directory holding the model file (downloaded on demand).
        min_confidence: Minimum detection score to report a face.
        max_faces: Maximum number of faces reported per frame.
        enabled: Initial enabled state (toggled in the GUI).
    """

    key = "face_detection"
    display_name = "Face Detection"

    def __init__(
        self,
        models_dir,
        min_confidence: float = 0.5,
        max_faces: int = 8,
        enabled: bool = True,
        use_gpu: bool = False,
    ) -> None:
        super().__init__(enabled=enabled)
        self._models = ModelManager(models_dir)
        self._min_confidence = min_confidence
        self._max_faces = max_faces
        self._use_gpu = use_gpu
        self._detector = None
        self._timestamps = MonotonicTimestamps()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load the BlazeFace model into a MediaPipe FaceDetector task."""
        if self.status is ModuleStatus.READY and self._detector is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python  # noqa: PLC0415
            from mediapipe.tasks.python import vision  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError(
                "mediapipe is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = self._models.ensure_model("face_detector")

        def build_options(base):
            return vision.FaceDetectorOptions(
                base_options=base,
                running_mode=mp_python.vision.RunningMode.VIDEO,
                min_detection_confidence=self._min_confidence,
            )

        try:
            self._detector, delegate = create_task_with_fallback(
                build_options,
                vision.FaceDetector.create_from_options,
                model_path,
                use_gpu=self._use_gpu,
                module_name="face_detection",
            )
        except Exception as exc:  # noqa: BLE001 — invalid/corrupt model etc.
            raise ModelLoadError(
                f"Face detector model could not be initialised: {exc}"
            ) from exc
        self.status = ModuleStatus.READY
        self.status_message = "" if delegate == "gpu" else f"delegate: {delegate}"
        log.info("Face detection model loaded (min confidence %.2f)", self._min_confidence)

    def unload(self) -> None:
        detector, self._detector = self._detector, None
        if detector is not None:
            try:
                detector.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        detector = self._detector
        if detector is None:
            raise VisionError("FaceDetectionModule.process called before load()")

        height, width = frame.shape[:2]
        mp_image = make_mp_image(frame)
        detections = detector.detect_for_video(mp_image, self._timestamps.next())

        for detection in detections.detections[: self._max_faces]:
            box = detection.bounding_box
            categories = detection.categories or []
            confidence = float(categories[0].score) if categories else None
            if confidence is not None and confidence < self._min_confidence:
                continue
            x, y, w, h = box_to_pixels(
                box.origin_x, box.origin_y, box.width, box.height, width, height
            )
            result.detections.append(
                FaceBox(
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    confidence=confidence,
                    source="detector",
                )
            )
