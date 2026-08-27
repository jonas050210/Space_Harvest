"""Gaze estimation: webcam-based approximate gaze mapping.

Pipeline::

    Face Mesh -> Eye/Iris Landmarks -> Eye Geometry -> Head Pose
        -> Calibration (optional) -> GazeEstimator -> Screen Coordinates

The output is explicitly an **estimate** ("Estimated Gaze") from a normal
webcam — never a medical or precision-grade measurement. Without a
calibration profile a documented heuristic mapping is used and the
confidence is capped; with a calibration profile an affine regression
(including head pose terms) maps features to screen coordinates.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional, Sequence

import numpy as np

from app.config.calibration import CalibrationProfile
from app.core.types import EyeData, GazePoint, HeadPose, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule
from app.vision.eye.geometry import (
    both_eyes,
    mean_iris_position,
    mean_opening,
    tracked_eyes,
)
from app.vision.eye.smoothing import GazeSmoother

log = get_logger("vision.eye.gaze")

#: Uncalibrated fallback mapping constants (documented heuristics):
#: iris movement gain per eye box, and head-pose compensation in
#: normalized units per degree. Tuned on frontal webcam geometry.
_GAIN_H = 2.4
_GAIN_V = 2.0
_HEAD_COMP_DEG = 0.016  # per degree of yaw/pitch

#: Confidence caps.
_MAX_UNCALIBRATED_CONFIDENCE = 0.70
_MAX_CALIBRATED_CONFIDENCE = 0.97
_CONF_OUT_OF_BOUNDS = 0.55

#: Stability window for the jitter-based confidence term.
_STABILITY_WINDOW = 12


def gaze_features_from_result(
    result: VisionResult,
) -> Optional[tuple[float, float, float, float]]:
    """Gaze features from a pipeline result: (iris_h, iris_v, yaw, pitch).

    Used by the gaze module *and* by calibration sampling, so both always
    agree on the feature definition.
    """
    eyes = result.eyes if result.eyes else []
    position = mean_iris_position(eyes)
    if position is None:
        return None
    pose = result.head_pose if result.head_pose and result.head_pose.valid else None
    yaw = float(pose.yaw) if pose else 0.0
    pitch = float(pose.pitch) if pose else 0.0
    return position[0], position[1], yaw, pitch


def estimate_confidence(
    eyes: Sequence[EyeData],
    head_pose: Optional[HeadPose],
    calibrated: bool,
    within_bounds: bool,
    recent_raw: Sequence[tuple[float, float]],
) -> float:
    """Heuristic confidence 0..1 combining data quality factors.

    Factors: number of tracked eyes, eye openness, head pose magnitude,
    gaze stability (jitter of recent raw estimates), calibration state.
    This is a *relative* quality indicator, not a statistical probability.
    """
    visible = tracked_eyes(eyes)
    if not visible:
        return 0.0

    factor = 1.0

    # Eye coverage.
    factor *= 1.0 if len(visible) >= 2 else 0.75

    # Eye openness (EAR): below ~0.12 no useful iris data.
    opening = mean_opening(visible)
    if opening is None:
        factor *= 0.4
    else:
        factor *= float(np.clip((opening - 0.12) / (0.26 - 0.12), 0.2, 1.0))

    # Head pose magnitude: extreme angles degrade the iris view.
    if head_pose is not None and head_pose.valid:
        magnitude = abs(head_pose.yaw) + abs(head_pose.pitch)
        factor *= float(np.clip(1.0 - magnitude / 70.0, 0.5, 1.0))
    else:
        factor *= 0.85

    # Stability: variance of recent raw (unsmoothed) estimates.
    if len(recent_raw) >= 4:
        raw = np.asarray(recent_raw, dtype=np.float64)
        variance = float(raw.var(axis=0).sum())
        factor *= float(np.clip(1.0 - variance / 0.006, 0.3, 1.0))

    # Calibration state.
    if calibrated:
        factor *= 1.0 if within_bounds else _CONF_OUT_OF_BOUNDS
        factor = min(factor, _MAX_CALIBRATED_CONFIDENCE)
    else:
        factor = min(factor, _MAX_UNCALIBRATED_CONFIDENCE)

    return round(float(np.clip(factor, 0.0, 1.0)), 3)


class GazeEstimator:
    """Maps gaze features to normalized screen coordinates.

    Args:
        smoother: Optional 2-D smoother applied to the raw estimate.
        clock: Injectable clock (tests).
    """

    def __init__(
        self,
        smoother: Optional[GazeSmoother] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._smoother = smoother
        self._clock = clock
        self._profile: Optional[CalibrationProfile] = None
        self._recent_raw: deque[tuple[float, float]] = deque(maxlen=_STABILITY_WINDOW)

    # ------------------------------------------------------------------
    @property
    def profile(self) -> Optional[CalibrationProfile]:
        return self._profile

    def set_profile(self, profile: Optional[CalibrationProfile]) -> None:
        """Activate (or clear) a calibration profile."""
        self._profile = profile
        if profile is not None:
            log.info("Gaze estimator now uses calibration profile (%s)", profile.quality)
        else:
            log.info("Gaze estimator switched to uncalibrated heuristic mode")

    def reset(self) -> None:
        """Clear smoothing + stability history (new camera session)."""
        self._recent_raw.clear()
        if self._smoother is not None:
            self._smoother.reset()

    # ------------------------------------------------------------------
    def estimate(
        self,
        features: tuple[float, float, float, float],
        eyes: Sequence[EyeData],
        head_pose: Optional[HeadPose],
    ) -> GazePoint:
        """Estimate the gaze point from features + context. Never raises."""
        iris_h, iris_v, yaw, pitch = features

        profile = self._profile
        if profile is not None:
            x, y, within_bounds = profile.predict(features)
            calibrated = True
        else:
            # Documented heuristic: iris offset from eye-box centre, with
            # head-pose compensation (head turns shift the iris in the box
            # even when the gaze target is unchanged). Sign conventions
            # follow the head-pose module: yaw > 0 = head turned right,
            # pitch > 0 = head tilted down.
            x = 0.5 + (iris_h - 0.5) * _GAIN_H + yaw * _HEAD_COMP_DEG
            y = 0.5 + (iris_v - 0.5) * _GAIN_V + pitch * _HEAD_COMP_DEG
            x = float(np.clip(x, 0.0, 1.0))
            y = float(np.clip(y, 0.0, 1.0))
            within_bounds = False
            calibrated = False

        raw = (float(x), float(y))
        self._recent_raw.append(raw)

        if self._smoother is not None:
            x, y = self._smoother.smooth(x, y)

        confidence = estimate_confidence(
            eyes=eyes,
            head_pose=head_pose,
            calibrated=calibrated,
            within_bounds=within_bounds,
            recent_raw=self._recent_raw,
        )
        return GazePoint(
            x=float(np.clip(x, 0.0, 1.0)),
            y=float(np.clip(y, 0.0, 1.0)),
            confidence=confidence,
            calibrated=calibrated,
            valid=True,
        )


class GazeModule(VisionModule):
    """Vision module: turns shared mesh + head pose into a gaze point.

    Consumes the landmarks the FaceMeshModule already produced (and the
    HeadPoseModule result if enabled) — no additional inference.
    """

    key = "gaze_estimation"
    display_name = "Gaze Estimation"

    def __init__(
        self,
        enabled: bool = True,
        smoothing: str = "medium",
        calibration_store=None,
    ) -> None:
        super().__init__(enabled=enabled)
        self._smoother = GazeSmoother(strength=smoothing)
        self._estimator = GazeEstimator(smoother=self._smoother)
        if calibration_store is not None:
            self._estimator.set_profile(calibration_store.profile)

    def load(self) -> None:
        self.status_message = ""

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_smoothing(self, strength: str) -> None:
        self._smoother.set_strength(strength)

    def set_profile(self, profile: Optional[CalibrationProfile]) -> None:
        self._estimator.set_profile(profile)

    def reset(self) -> None:
        """New camera session: forget smoothing/calibration state."""
        self._estimator.reset()

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarks = result.first_raw_mesh()
        if landmarks is None:
            result.gaze = None
            return
        eyes = result.eyes if result.eyes else both_eyes(landmarks)
        position = mean_iris_position(eyes)
        if position is None:
            result.gaze = None
            return
        pose = result.head_pose
        yaw = float(pose.yaw) if pose and pose.valid else 0.0
        pitch = float(pose.pitch) if pose and pose.valid else 0.0
        features = (position[0], position[1], yaw, pitch)
        try:
            result.gaze = self._estimator.estimate(features, eyes, result.head_pose)
        except Exception:  # noqa: BLE001 — pipeline isolates failures
            log.exception("Gaze estimation failed on frame")
            result.gaze = None
