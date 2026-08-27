"""Body pose module (MediaPipe PoseLandmarker, lite model).

Detects the 33-landmark body pose of the most prominent person. Produces
BodyData (landmarks, visibility, head, shoulder line, arm states,
smoothed movement). Runs independently of the face/hand/object models —
one pose inference per frame (with performance-mode frame skipping).
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from app.core.errors import ModelLoadError, VisionError
from app.core.types import BodyData, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.body.analysis import (
    LandmarkSmoother,
    MovementTracker,
    arm_angles,
    arm_states,
    centroid,
    head_position,
    shoulder_angle,
    shoulder_line,
)
from app.vision.face._mediapipe_helpers import (
    MonotonicTimestamps,
    create_task_with_fallback,
    make_mp_image,
)
from app.vision.model_manager import ModelManager

log = get_logger("vision.body.pose")

#: Movement speed (px/frame) above which the body counts as "moving".
_MOVING_THRESHOLD = 2.5


class BodyPoseModule(VisionModule):
    """MediaPipe PoseLandmarker: 33 landmarks + body analysis."""

    key = "body_tracking"
    display_name = "Body Tracking"

    def __init__(
        self,
        models_dir,
        enabled: bool = True,
        use_gpu: bool = False,
        frame_interval: int = 1,
        input_scale: float = 1.0,
    ) -> None:
        super().__init__(enabled=enabled)
        self._models = ModelManager(models_dir)
        self._use_gpu = use_gpu
        self._pose_landmarker = None
        self._timestamps = MonotonicTimestamps()
        self._movement = MovementTracker()
        self._smoother = LandmarkSmoother(alpha=0.45)
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        self._frame_counter = 0
        self._cached: Optional[BodyData] = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_performance_mode(self, frame_interval: int, input_scale: float) -> None:
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        log.info(
            "Body pose performance mode: every %d frame(s), scale %.2f",
            self._frame_interval,
            self._input_scale,
        )

    def reset(self) -> None:
        self._movement.reset()
        self._smoother.reset()
        self._cached = None

    # ------------------------------------------------------------------
    def load(self) -> None:
        if self.status is ModuleStatus.READY and self._pose_landmarker is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python  # noqa: PLC0415 — lazy
            from mediapipe.tasks.python import vision  # noqa: PLC0415 — lazy
        except ImportError as exc:
            raise ModelLoadError(
                "mediapipe is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = self._models.ensure_model("pose_landmarker")

        def build_options(base):
            return vision.PoseLandmarkerOptions(
                base_options=base,
                running_mode=mp_python.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_segmentation_masks=False,
            )

        try:
            self._pose_landmarker, delegate = create_task_with_fallback(
                build_options,
                vision.PoseLandmarker.create_from_options,
                model_path,
                use_gpu=self._use_gpu,
                module_name="body_tracking",
            )
        except Exception as exc:  # noqa: BLE001 — corrupt model etc.
            raise ModelLoadError(
                f"Pose landmarker model could not be initialised: {exc}"
            ) from exc
        self.status = ModuleStatus.READY
        self.status_message = "" if delegate == "gpu" else f"delegate: {delegate}"
        log.info("Body pose model loaded")

    def unload(self) -> None:
        landmarker, self._pose_landmarker = self._pose_landmarker, None
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarker = self._pose_landmarker
        if landmarker is None:
            raise VisionError("BodyPoseModule.process called before load()")

        full_h, full_w = frame.shape[:2]

        # Frame skipping: reuse the cached body data between inferences,
        # but keep the movement tracker fed with the last centroid.
        self._frame_counter += 1
        if (
            self._frame_interval > 1
            and self._cached is not None
            and self._frame_counter % self._frame_interval != 0
        ):
            result.body = self._cached
            if self._cached.centroid is not None:
                self._movement.update(self._cached.centroid)
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
        inverse = 1.0 / self._input_scale
        mp_image = make_mp_image(inference_frame)
        output = landmarker.detect_for_video(mp_image, self._timestamps.next())

        body: Optional[BodyData] = None
        if output.pose_landmarks:
            landmarks_raw = output.pose_landmarks[0]
            points = np.array(
                [[lm.x * width, lm.y * height, lm.z] for lm in landmarks_raw],
                dtype=np.float32,
            )
            if inverse != 1.0:
                points[:, 0] *= inverse
                points[:, 1] *= inverse
            visibility = np.array(
                [getattr(lm, "visibility", 1.0) or 1.0 for lm in landmarks_raw],
                dtype=np.float32,
            )
            # Smooth raw jitter before analysis/overlay (x/y only).
            points = self._smoother.smooth(points)
            center = centroid(points, visibility)
            movement = self._movement.update(center) if center else None
            movement_speed = (
                float(np.hypot(*movement)) if movement is not None else 0.0
            )
            body = BodyData(
                landmarks=points,
                visibility=visibility,
                present=True,
                head_position=head_position(points),
                shoulder_line=shoulder_line(points),
                arm_states=arm_states(points, visibility),
                arm_angles=arm_angles(points, visibility),
                shoulder_angle_deg=shoulder_angle(points),
                movement=movement,
                movement_speed=round(movement_speed, 2),
                centroid=center,
            )
        else:
            self._smoother.reset()

        self._cached = body
        result.body = body
