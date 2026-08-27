"""Geometric body analysis from the 33 MediaPipe pose landmarks.

Pure functions (never raise on bad data): arm states via wrist position
relative to the shoulder, shoulder line, body centroid and smoothed
movement. Subject perspective labels ("left"/"right" = the person's arm).
"""

from __future__ import annotations

import math
from collections import deque
from typing import Optional

import numpy as np

#: Landmark ids of interest.
_L_NOSE = 0
_L_SHOULDER_LEFT = 11
_L_SHOULDER_RIGHT = 12
_L_ELBOW_LEFT = 13
_L_ELBOW_RIGHT = 14
_L_WRIST_LEFT = 15
_L_WRIST_RIGHT = 16

#: Minimum visibility for a joint to count as usable.
_MIN_VISIBILITY = 0.5

#: Vertical threshold: wrist this far above the shoulder (as a fraction
#: of the shoulder width) counts as RAISED.
_RAISE_RATIO = 0.5
#: Horizontal threshold: wrist this far outside the shoulder counts as OUT.
_OUT_RATIO = 0.6


def _point(landmarks: np.ndarray, index: int) -> Optional[tuple[float, float]]:
    if len(landmarks) <= index:
        return None
    return float(landmarks[index, 0]), float(landmarks[index, 1])


def arm_states(landmarks: np.ndarray, visibility: Optional[np.ndarray] = None) -> dict[str, str]:
    """Arm states for left/right (subject perspective): RAISED/OUT/
    NEUTRAL/DOWN/UNKNOWN. Pure geometry, no ML."""
    states: dict[str, str] = {}
    for side, shoulder_id, elbow_id, wrist_id in (
        ("left", _L_SHOULDER_LEFT, _L_ELBOW_LEFT, _L_WRIST_LEFT),
        ("right", _L_SHOULDER_RIGHT, _L_ELBOW_RIGHT, _L_WRIST_RIGHT),
    ):
        shoulder = _point(landmarks, shoulder_id)
        wrist = _point(landmarks, wrist_id)
        if shoulder is None or wrist is None:
            states[side] = "UNKNOWN"
            continue
        if visibility is not None and len(visibility) > max(shoulder_id, wrist_id):
            if (
                visibility[shoulder_id] < _MIN_VISIBILITY
                or visibility[wrist_id] < _MIN_VISIBILITY
            ):
                states[side] = "UNKNOWN"
                continue

        other_shoulder = (
            _point(landmarks, _L_SHOULDER_RIGHT)
            if side == "left"
            else _point(landmarks, _L_SHOULDER_LEFT)
        )
        shoulder_width = (
            abs(shoulder[0] - other_shoulder[0])
            if other_shoulder is not None
            else 100.0
        )
        if shoulder_width < 1e-6:
            shoulder_width = 100.0

        dy = shoulder[1] - wrist[1]   # > 0 = wrist above shoulder (image y down)
        dx = wrist[0] - shoulder[0]   # > 0 = wrist outside (away from body center)

        if dy > _RAISE_RATIO * shoulder_width:
            states[side] = "RAISED"
        elif abs(dx) > _OUT_RATIO * shoulder_width:
            states[side] = "OUT"
        elif dy < -0.3 * shoulder_width:
            states[side] = "DOWN"
        else:
            states[side] = "NEUTRAL"
    return states


def shoulder_line(landmarks: np.ndarray) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """((left shoulder), (right shoulder)) in pixel coordinates."""
    left = _point(landmarks, _L_SHOULDER_LEFT)
    right = _point(landmarks, _L_SHOULDER_RIGHT)
    if left is None or right is None:
        return None
    return left, right


def arm_angles(
    landmarks: np.ndarray,
    visibility: Optional[np.ndarray] = None,
) -> dict[str, Optional[float]]:
    """Elbow angle per arm (degrees, 0-180): shoulder -> elbow -> wrist.

    Returns None for an arm whose joints are not visible/usable —
    the UI shows "—" instead of a guessed value.
    """
    angles: dict[str, Optional[float]] = {}
    for side, shoulder_id, elbow_id, wrist_id in (
        ("left", _L_SHOULDER_LEFT, _L_ELBOW_LEFT, _L_WRIST_LEFT),
        ("right", _L_SHOULDER_RIGHT, _L_ELBOW_RIGHT, _L_WRIST_RIGHT),
    ):
        if visibility is not None and len(visibility) > max(
            shoulder_id, elbow_id, wrist_id
        ):
            if any(
                visibility[joint] < _MIN_VISIBILITY
                for joint in (shoulder_id, elbow_id, wrist_id)
            ):
                angles[side] = None
                continue
        shoulder = _point(landmarks, shoulder_id)
        elbow = _point(landmarks, elbow_id)
        wrist = _point(landmarks, wrist_id)
        if None in (shoulder, elbow, wrist):
            angles[side] = None
            continue
        v1 = np.array([shoulder[0] - elbow[0], shoulder[1] - elbow[1]])
        v2 = np.array([wrist[0] - elbow[0], wrist[1] - elbow[1]])
        norm1 = float(np.hypot(*v1))
        norm2 = float(np.hypot(*v2))
        if norm1 < 1e-6 or norm2 < 1e-6:
            angles[side] = None
            continue
        cos_angle = float(np.dot(v1, v2) / (norm1 * norm2))
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angles[side] = round(float(np.degrees(np.arccos(cos_angle))), 1)
    return angles


def shoulder_angle(landmarks: np.ndarray) -> Optional[float]:
    """Tilt of the shoulder line (degrees in [-90, 90], 0 = level;
    positive = the right shoulder appears higher in image coordinates).
    None when shoulders are not visible."""
    line = shoulder_line(landmarks)
    if line is None:
        return None
    (lx, ly), (rx, ry) = line
    angle = float(np.degrees(np.arctan2(ly - ry, rx - lx)))
    # Fold into [-90, 90]: a line is identical rotated by 180°.
    if angle > 90.0:
        angle -= 180.0
    elif angle < -90.0:
        angle += 180.0
    return round(angle, 1)


class LandmarkSmoother:
    """Per-landmark EMA smoothing for jitter-free overlays.

    Only x/y are smoothed (z stays raw); visibility is not altered.
    The first frame seeds the state; ``reset()`` re-seeds on the next
    update (e.g. after the person disappeared).
    """

    def __init__(self, alpha: float = 0.45) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self._alpha = alpha
        self._state: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._state = None

    def smooth(self, landmarks: np.ndarray) -> np.ndarray:
        """Return the smoothed landmark array (same shape as input)."""
        points = np.asarray(landmarks, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] < 3:
            return points
        if self._state is None or self._state.shape != points.shape:
            self._state = points.copy()
            return points.copy()
        smoothed = points.copy()
        smoothed[:, :2] = (
            self._alpha * points[:, :2]
            + (1.0 - self._alpha) * self._state[:, :2]
        )
        self._state = smoothed.copy()
        return smoothed


def head_position(landmarks: np.ndarray) -> Optional[tuple[float, float]]:
    return _point(landmarks, _L_NOSE)


def centroid(landmarks: np.ndarray, visibility: Optional[np.ndarray] = None) -> Optional[tuple[float, float]]:
    """Mean of usable upper-body joints (head, shoulders, elbows, wrists)."""
    indices = (
        _L_NOSE,
        _L_SHOULDER_LEFT, _L_SHOULDER_RIGHT,
        _L_ELBOW_LEFT, _L_ELBOW_RIGHT,
        _L_WRIST_LEFT, _L_WRIST_RIGHT,
    )
    points: list[tuple[float, float]] = []
    for index in indices:
        point = _point(landmarks, index)
        if point is None:
            continue
        if visibility is not None and len(visibility) > index and visibility[index] < _MIN_VISIBILITY:
            continue
        points.append(point)
    if not points:
        return None
    array = np.asarray(points, dtype=np.float32)
    return float(array[:, 0].mean()), float(array[:, 1].mean())


class MovementTracker:
    """Smoothed body movement (EMA of the centroid shift per frame)."""

    def __init__(self, window: int = 5) -> None:
        self._history: deque[tuple[float, float]] = deque(maxlen=max(2, window))
        self._velocity: Optional[tuple[float, float]] = None

    def update(self, point: tuple[float, float]) -> Optional[tuple[float, float]]:
        """Feed the current centroid; returns the smoothed velocity."""
        if self._history:
            previous = self._history[-1]
            raw = (point[0] - previous[0], point[1] - previous[1])
            if self._velocity is None:
                self._velocity = raw
            else:
                self._velocity = (
                    self._velocity[0] * 0.7 + raw[0] * 0.3,
                    self._velocity[1] * 0.7 + raw[1] * 0.3,
                )
        self._history.append(point)
        return self._velocity

    @property
    def velocity(self) -> Optional[tuple[float, float]]:
        return self._velocity

    def speed(self) -> float:
        if self._velocity is None:
            return 0.0
        return float(math.hypot(*self._velocity))

    def reset(self) -> None:
        self._history.clear()
        self._velocity = None
