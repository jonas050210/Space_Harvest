"""Shared eye geometry derived from the 478-point face mesh.

This is the single source of truth for eye-related landmark math. Eye
tracking, gaze estimation and blink detection all reuse these helpers, so
no module ever duplicates landmark index handling. Everything works on the
landmark array that :class:`~app.vision.face.face_mesh_module.FaceMeshModule`
already produces — no additional inference is performed.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from app.core.types import EyeData
from app.vision.face.mesh_topology import (
    FACEMESH_LEFT_EYE,
    FACEMESH_LEFT_IRIS,
    FACEMESH_RIGHT_EYE,
    FACEMESH_RIGHT_IRIS,
)

#: All landmark indices of each eye (from the official topology sets).
LEFT_EYE_INDICES: tuple[int, ...] = tuple(
    sorted({i for pair in FACEMESH_LEFT_EYE for i in pair})
)
RIGHT_EYE_INDICES: tuple[int, ...] = tuple(
    sorted({i for pair in FACEMESH_RIGHT_EYE for i in pair})
)

#: Iris ring landmarks (4 per eye).
LEFT_IRIS_INDICES: tuple[int, ...] = tuple(
    sorted({i for pair in FACEMESH_LEFT_IRIS for i in pair})
)
RIGHT_IRIS_INDICES: tuple[int, ...] = tuple(
    sorted({i for pair in FACEMESH_RIGHT_IRIS for i in pair})
)

#: Canonical six-point EAR sets (p1..p6: outer corner, top, top-inner,
#: inner corner, bottom-inner, bottom — MediaPipe convention).
EAR_SETS: dict[str, tuple[int, ...]] = {
    "left": (362, 385, 387, 263, 373, 380),
    "right": (33, 160, 158, 133, 153, 144),
}

#: Eye state thresholds (empirical EAR values for the 6-point sets).
OPEN_THRESHOLD = 0.20   # above: eye clearly open
CLOSED_THRESHOLD = 0.13  # below: eye essentially closed


def _points(
    landmarks: np.ndarray, indices: Sequence[int]
) -> Optional[np.ndarray]:
    """Return the (N, 2) pixel points for the indices, or None if the
    landmark array is too short (bad data)."""
    if landmarks is None or len(landmarks) <= max(indices, default=-1):
        return None
    return np.asarray(landmarks, dtype=np.float32)[list(indices), :2]


def eye_box(
    landmarks: np.ndarray, side: str
) -> Optional[tuple[int, int, int, int]]:
    """Bounding box (x, y, w, h in pixels) of one eye's landmarks."""
    indices = LEFT_EYE_INDICES if side == "left" else RIGHT_EYE_INDICES
    points = _points(landmarks, indices)
    if points is None or len(points) == 0:
        return None
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)
    w, h = x_max - x_min, y_max - y_min
    if w < 1.0 or h < 1.0:
        return None
    return int(x_min), int(y_min), max(1, int(w)), max(1, int(h))


def ear(landmarks: np.ndarray, side: str) -> Optional[float]:
    """Eye Aspect Ratio for one eye (0 = closed, ~0.3 = open).

    EAR = (d(p2,p6) + d(p3,p5)) / (2 * d(p1,p4))
    """
    indices = EAR_SETS[side]
    points = _points(landmarks, indices)
    if points is None:
        return None
    p1, p2, p3, p4, p5, p6 = points

    def dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    horizontal = dist(p1, p4)
    if horizontal < 1e-6:
        return None
    return (dist(p2, p6) + dist(p3, p5)) / (2.0 * horizontal)


def iris_center(landmarks: np.ndarray, side: str) -> Optional[tuple[float, float]]:
    """Mean of the 4 iris ring landmarks (pixel coordinates)."""
    indices = LEFT_IRIS_INDICES if side == "left" else RIGHT_IRIS_INDICES
    points = _points(landmarks, indices)
    if points is None or len(points) == 0:
        return None
    center = points.mean(axis=0)
    return float(center[0]), float(center[1])


def iris_relative(
    iris: tuple[float, float], box: tuple[int, int, int, int]
) -> tuple[float, float]:
    """Iris position normalized within the eye box: (h, v), each 0..1."""
    x, y, w, h = box
    rel_h = (iris[0] - x) / w
    rel_v = (iris[1] - y) / h
    return float(np.clip(rel_h, 0.0, 1.0)), float(np.clip(rel_v, 0.0, 1.0))


def eye_from_landmarks(landmarks: np.ndarray, side: str) -> EyeData:
    """Full per-eye analysis for one side; never raises on bad data."""
    data = EyeData(side=side)
    box = eye_box(landmarks, side)
    data.eye_box = box

    opening = ear(landmarks, side)
    data.opening = None if opening is None else round(float(opening), 4)
    if opening is None or opening < CLOSED_THRESHOLD:
        data.state = "closed"
        # Iris data while closed is unreliable (landmarks collapse).
        return data

    center = iris_center(landmarks, side)
    if center is None or box is None:
        data.state = "lost"
        return data
    data.iris_center = center
    data.iris_h, data.iris_v = iris_relative(center, box)
    data.state = "tracked"
    return data


def both_eyes(landmarks: np.ndarray) -> list[EyeData]:
    """Analyse both eyes of one face (subject perspective labels)."""
    if landmarks is None or len(landmarks) < 478:
        return []
    return [
        eye_from_landmarks(landmarks, "left"),
        eye_from_landmarks(landmarks, "right"),
    ]


def tracked_eyes(eyes: Sequence[EyeData]) -> list[EyeData]:
    """Only eyes with usable iris data."""
    return [e for e in eyes if e.state == "tracked" and e.iris_center is not None]


def mean_iris_position(eyes: Sequence[EyeData]) -> Optional[tuple[float, float]]:
    """Mean (h, v) iris position over the visible eyes."""
    visible = tracked_eyes(eyes)
    if not visible:
        return None
    hs = [e.iris_h for e in visible if e.iris_h is not None]
    vs = [e.iris_v for e in visible if e.iris_v is not None]
    if not hs or not vs:
        return None
    return float(np.mean(hs)), float(np.mean(vs))


def mean_opening(eyes: Sequence[EyeData]) -> Optional[float]:
    """Mean EAR over eyes with valid opening values."""
    values = [e.opening for e in eyes if e.opening is not None]
    if not values:
        return None
    return float(np.mean(values))


def eye_box_diagonal(eyes: Sequence[EyeData]) -> Optional[float]:
    """Mean eye-box diagonal in pixels (scales iris drawing)."""
    diagonals = [
        math.hypot(box[2], box[3])
        for e in eyes
        if (box := e.eye_box) is not None
    ]
    return float(np.mean(diagonals)) if diagonals else None
