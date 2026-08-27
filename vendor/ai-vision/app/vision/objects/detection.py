"""Object detection module (MediaPipe ObjectDetector, EfficientDet-Lite0).

Produces raw detections (bounding box, class name from the COCO label map,
confidence). Stable IDs are assigned afterwards by ObjectTrackingModule —
this module stays a thin inference wrapper. Runs fully locally.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from app.core.errors import ModelLoadError, VisionError
from app.core.types import Box, ObjectDetection, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.face._mediapipe_helpers import (
    MonotonicTimestamps,
    box_to_pixels,
    create_task_with_fallback,
    make_mp_image,
)
from app.vision.model_manager import ModelManager
from app.vision.objects.labels import COCO_LABELS

log = get_logger("vision.objects.detection")


class ObjectDetectionModule(VisionModule):
    """EfficientDet-Lite0 object detector (80 COCO classes).

    Args:
        models_dir: Directory holding the model (downloaded on demand).
        min_confidence: Minimum score to report a detection.
        max_objects: Maximum detections reported per frame.
        enabled: Initial enabled state.
    """

    key = "object_detection"
    display_name = "Object Detection"

    def __init__(
        self,
        models_dir,
        min_confidence: float = 0.5,
        max_objects: int = 20,
        enabled: bool = True,
        use_gpu: bool = False,
        frame_interval: int = 1,
        input_scale: float = 1.0,
    ) -> None:
        super().__init__(enabled=enabled)
        self._models = ModelManager(models_dir)
        self._min_confidence = min_confidence
        self._max_objects = max_objects
        self._use_gpu = use_gpu
        self._detector = None
        self._timestamps = MonotonicTimestamps()
        # Performance mode support: run inference every N frames and/or on
        # a downscaled input; between runs the last detections are reused.
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        self._frame_counter = 0
        self._cached: Optional[list] = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_confidence(self, value: float) -> None:
        self._min_confidence = float(value)
        log.info("Object detection confidence set to %.2f", self._min_confidence)

    def set_max_objects(self, value: int) -> None:
        self._max_objects = int(value)
        log.info("Object detection max objects set to %d", self._max_objects)

    def set_performance_mode(self, frame_interval: int, input_scale: float) -> None:
        """Apply a vision performance mode (called by the controller)."""
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        log.info(
            "Object detection performance mode: every %d frame(s), scale %.2f",
            self._frame_interval,
            self._input_scale,
        )

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load the EfficientDet-Lite0 model into a MediaPipe task."""
        if self.status is ModuleStatus.READY and self._detector is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python  # noqa: PLC0415 — lazy
            from mediapipe.tasks.python import vision  # noqa: PLC0415 — lazy
        except ImportError as exc:
            raise ModelLoadError(
                "mediapipe is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = self._models.ensure_model("object_detector")

        def build_options(base):
            return vision.ObjectDetectorOptions(
                base_options=base,
                running_mode=mp_python.vision.RunningMode.VIDEO,
                max_results=self._max_objects,
                score_threshold=self._min_confidence,
            )

        try:
            self._detector, delegate = create_task_with_fallback(
                build_options,
                vision.ObjectDetector.create_from_options,
                model_path,
                use_gpu=self._use_gpu,
                module_name="object_detection",
            )
        except Exception as exc:  # noqa: BLE001 — corrupt model etc.
            raise ModelLoadError(
                f"Object detector model could not be initialised: {exc}"
            ) from exc
        self.status = ModuleStatus.READY
        self.status_message = "" if delegate == "gpu" else f"delegate: {delegate}"
        log.info(
            "Object detection model loaded (min confidence %.2f, max %d objects)",
            self._min_confidence,
            self._max_objects,
        )

    def unload(self) -> None:
        detector, self._detector = self._detector, None
        if detector is not None:
            try:
                detector.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        detector = self._detector
        if detector is None:
            raise VisionError("ObjectDetectionModule.process called before load()")

        # Frame skipping: reuse the cached detections between inferences.
        self._frame_counter += 1
        if (
            self._frame_interval > 1
            and self._cached is not None
            and self._frame_counter % self._frame_interval != 0
        ):
            result.object_detections = list(self._cached)
            return

        inference_frame = frame
        if self._input_scale < 1.0:
            inference_frame = cv2.resize(
                frame,
                (
                    max(1, int(frame.shape[1] * self._input_scale)),
                    max(1, int(frame.shape[0] * self._input_scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )

        height, width = inference_frame.shape[:2]
        mp_image = make_mp_image(inference_frame)
        detections = detector.detect_for_video(mp_image, self._timestamps.next())

        # Scale boxes back to full-frame pixel coordinates.
        inverse = 1.0 / self._input_scale
        detections_out: list[ObjectDetection] = []
        for detection in detections.detections[: self._max_objects]:
            box = detection.bounding_box
            categories = detection.categories or []
            if not categories:
                continue
            category = categories[0]
            confidence = float(category.score)
            if confidence < self._min_confidence:
                continue
            class_name = self._class_name(category)
            if not class_name:
                continue
            x, y, w, h = box_to_pixels(
                box.origin_x, box.origin_y, box.width, box.height, width, height
            )
            detections_out.append(
                ObjectDetection(
                    id=0,  # assigned by ObjectTrackingModule
                    class_name=class_name,
                    confidence=confidence,
                    bbox=Box(
                        int(round(x * inverse)),
                        int(round(y * inverse)),
                        max(1, int(round(w * inverse))),
                        max(1, int(round(h * inverse))),
                    ),
                )
            )
        self._cached = detections_out
        result.object_detections = list(detections_out)

    @staticmethod
    def _class_name(category) -> str:
        """Resolve the category name (model metadata or vendored COCO map).

        COCO category indices are 0-based (0 = person), the vendored tuple
        is shifted so that COCO_LABELS[0] == "person".
        """
        name = getattr(category, "category_name", None) or ""
        if name:
            return name
        index = int(getattr(category, "index", -1))
        if 0 <= index < len(COCO_LABELS):
            return COCO_LABELS[index]
        return ""
