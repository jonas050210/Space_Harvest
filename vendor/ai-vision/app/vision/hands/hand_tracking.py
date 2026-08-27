"""Hand tracking module (MediaPipe HandLandmarker).

Detects up to ``max_hands`` hands with 21 landmarks each, handedness
(Left/Right) and per-landmark presence. Hands get stable IDs across
frames via :class:`HandTracker`. Runs fully locally; landmarks are reused
by the gesture module (no additional inference).
"""

from __future__ import annotations

import numpy as np

import cv2

from app.core.errors import ModelLoadError, VisionError
from app.core.types import TrackedHand, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.face._mediapipe_helpers import (
    MonotonicTimestamps,
    create_task_with_fallback,
    make_mp_image,
)
from app.vision.hands.geometry import finger_states, hand_bbox
from app.vision.hands.tracker import HandTracker
from app.vision.model_manager import ModelManager

log = get_logger("vision.hands.tracking")


class HandTrackingModule(VisionModule):
    """MediaPipe HandLandmarker with stable per-hand IDs.

    Args:
        models_dir: Directory holding the model (downloaded on demand).
        max_hands: Maximum number of hands detected per frame.
        enabled: Initial enabled state.
    """

    key = "hand_tracking"
    display_name = "Hand Tracking"

    def __init__(
        self,
        models_dir,
        max_hands: int = 2,
        enabled: bool = True,
        tracker: HandTracker | None = None,
        use_gpu: bool = False,
        frame_interval: int = 1,
        input_scale: float = 1.0,
    ) -> None:
        super().__init__(enabled=enabled)
        self._models = ModelManager(models_dir)
        self._max_hands = max_hands
        self._use_gpu = use_gpu
        self._landmarker = None
        self._tracker = tracker or HandTracker()
        self._timestamps = MonotonicTimestamps()
        # Performance mode support: inference every N frames and/or on a
        # downscaled input; between inferences the last raw hands are
        # reused and only the cheap tracking step keeps running.
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        self._frame_counter = 0
        self._cached: list[TrackedHand] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_max_hands(self, value: int) -> None:
        self._max_hands = int(value)
        log.info("Hand tracking max hands set to %d", self._max_hands)

    def set_performance_mode(self, frame_interval: int, input_scale: float) -> None:
        """Apply a vision performance mode (called by the controller)."""
        self._frame_interval = max(1, int(frame_interval))
        self._input_scale = min(1.0, max(0.25, float(input_scale)))
        log.info(
            "Hand tracking performance mode: every %d frame(s), scale %.2f",
            self._frame_interval,
            self._input_scale,
        )

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load the HandLandmarker model."""
        if self.status is ModuleStatus.READY and self._landmarker is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python  # noqa: PLC0415 — lazy
            from mediapipe.tasks.python import vision  # noqa: PLC0415 — lazy
        except ImportError as exc:
            raise ModelLoadError(
                "mediapipe is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = self._models.ensure_model("hand_landmarker")

        def build_options(base):
            return vision.HandLandmarkerOptions(
                base_options=base,
                running_mode=mp_python.vision.RunningMode.VIDEO,
                num_hands=self._max_hands,
            )

        try:
            self._landmarker, delegate = create_task_with_fallback(
                build_options,
                vision.HandLandmarker.create_from_options,
                model_path,
                use_gpu=self._use_gpu,
                module_name="hand_tracking",
            )
        except Exception as exc:  # noqa: BLE001 — corrupt model etc.
            raise ModelLoadError(
                f"Hand landmarker model could not be initialised: {exc}"
            ) from exc
        self.status = ModuleStatus.READY
        self.status_message = "" if delegate == "gpu" else f"delegate: {delegate}"
        log.info("Hand tracking model loaded (max hands %d)", self._max_hands)

    def unload(self) -> None:
        landmarker, self._landmarker = self._landmarker, None
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception:  # noqa: BLE001
                pass

    def reset(self) -> None:
        self._tracker.reset()

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarker = self._landmarker
        if landmarker is None:
            raise VisionError("HandTrackingModule.process called before load()")

        full_h, full_w = frame.shape[:2]

        # Frame skipping: reuse the cached raw hands between inferences,
        # but keep running the cheap tracking step every frame.
        self._frame_counter += 1
        if (
            self._frame_interval > 1
            and self._cached is not None
            and self._frame_counter % self._frame_interval != 0
        ):
            self._track(result, self._cached, full_w, full_h)
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

        hands: list[TrackedHand] = []
        for landmarks, handedness in zip(
            output.hand_landmarks, output.handedness
        ):
            points = np.array(
                [[lm.x * width, lm.y * height, lm.z] for lm in landmarks],
                dtype=np.float32,
            )
            if inverse != 1.0:
                points[:, 0] *= inverse
                points[:, 1] *= inverse
            bbox = hand_bbox(points)
            if bbox is None:
                continue
            handedness_name = ""
            handedness_score = 0.0
            if handedness and handedness[0].category_name:
                handedness_name = handedness[0].category_name
                handedness_score = float(handedness[0].score)
            hands.append(
                TrackedHand(
                    id=0,  # assigned by the tracker
                    handedness=handedness_name,
                    handedness_confidence=round(handedness_score, 4),
                    landmarks=points,
                    bbox=bbox,
                    finger_states=finger_states(points),
                )
            )

        self._cached = hands
        self._track(result, hands, full_w, full_h)

    def _track(
        self,
        result: VisionResult,
        hands: list[TrackedHand],
        width: int,
        height: int,
    ) -> None:
        try:
            result.hands = self._tracker.update(hands, width, height)
        except Exception:  # noqa: BLE001 — pipeline isolates failures
            log.exception("Hand tracking failed on frame")
            result.hands = []
