"""Geometric hand analysis from the 21 hand landmarks.

Finger states are computed with a rotation-invariant heuristic: a finger
counts as extended when its fingertip is farther from the wrist than its
PIP joint (folded fingers bring the tip closer to the palm). The thumb is
compared via its IP joint. All functions are pure and never raise on bad
data — they return conservative defaults instead.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.types import Box

#: Landmark ids: 0 = wrist, 1-4 thumb, 5-8 index, 9-12 middle,
#: 13-16 ring, 17-20 pinky. (tip, pip/ip) pairs used for extension tests.
_FINGER_LANDMARKS: dict[str, tuple[int, int, int]] = {
    # name: (mcp, joint, tip) — for the thumb the "joint" is the IP.
    "thumb": (1, 3, 4),
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}

#: Extension margin: tip distance must exceed joint distance by this
#: factor to count as extended (reduces flicker).
_EXTENSION_MARGIN = 1.05

#: Min hand size (px) for geometry to be considered usable.
_MIN_HAND_SIZE = 20.0


def hand_bbox(landmarks: np.ndarray, padding_ratio: float = 0.08) -> Optional[Box]:
    """Bounding box of the 21 landmarks (padded, unclamped — the annotator
    clamps during drawing)."""
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 21:
        return None
    xs, ys = points[:, 0], points[:, 1]
    x_min, x_max = float(xs.min()), float(xs.max())
    y_min, y_max = float(ys.min()), float(ys.max())
    pad_x = (x_max - x_min) * padding_ratio
    pad_y = (y_max - y_min) * padding_ratio
    x = max(0, int(x_min - pad_x))
    y = max(0, int(y_min - pad_y))
    w = max(1, int(x_max - x_min + 2 * pad_x) + 1)
    h = max(1, int(y_max - y_min + 2 * pad_y) + 1)
    return Box(x, y, w, h)


def hand_size(landmarks: np.ndarray) -> float:
    """Hand scale in pixels: wrist -> middle MCP distance (fallback:
    wrist -> middle tip, or bbox diagonal)."""
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 21:
        return 0.0
    wrist = points[0, :2]
    middle_mcp = points[9, :2]
    size = float(np.hypot(*(middle_mcp - wrist)))
    if size < 1.0:
        size = float(np.hypot(*(points[12, :2] - wrist)))
    if size < 1.0:
        box = hand_bbox(points)
        if box is not None:
            size = float(np.hypot(box.width, box.height))
    return size


def finger_states(landmarks: np.ndarray) -> dict[str, str]:
    """Per-finger states: "UP" (extended) / "DOWN" (folded) / "UNKNOWN".

    Pure geometric heuristic — no ML. Returns UNKNOWN for fingers whose
    geometry is too small or degenerate to decide.
    """
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 21:
        return {name: "UNKNOWN" for name in _FINGER_LANDMARKS}

    size = hand_size(points)
    if size < _MIN_HAND_SIZE:
        return {name: "UNKNOWN" for name in _FINGER_LANDMARKS}

    wrist = points[0, :2]
    states: dict[str, str] = {}
    for name, (_mcp, joint, tip) in _FINGER_LANDMARKS.items():
        tip_distance = float(np.hypot(*(points[tip, :2] - wrist)))
        joint_distance = float(np.hypot(*(points[joint, :2] - wrist)))
        if joint_distance < 1e-6:
            states[name] = "UNKNOWN"
            continue
        ratio = tip_distance / joint_distance
        if ratio >= _EXTENSION_MARGIN:
            states[name] = "UP"
        elif ratio < 1.0:
            states[name] = "DOWN"
        else:
            # In the hysteresis band the state is ambiguous.
            states[name] = "UNKNOWN"
    return states


def finger_state_margin(
    landmarks: np.ndarray, states: dict[str, str]
) -> float:
    """Mean normalized decision margin of the *decided* fingers (0..1).

    Ratio-based: |tip_distance / joint_distance - 1| — decisive when the
    ratio is clearly above (extended) or below (folded) 1. Used as the
    geometric plausibility basis of gesture confidence.
    """
    points = np.asarray(landmarks, dtype=np.float32)
    if hand_size(points) < _MIN_HAND_SIZE:
        return 0.0
    margins: list[float] = []
    wrist = points[0, :2]
    for name, state in states.items():
        if state not in ("UP", "DOWN"):
            continue
        _mcp, joint, tip = _FINGER_LANDMARKS[name]
        tip_distance = float(np.hypot(*(points[tip, :2] - wrist)))
        joint_distance = float(np.hypot(*(points[joint, :2] - wrist)))
        if joint_distance < 1e-6:
            continue
        raw = abs(tip_distance / joint_distance - 1.0)
        margins.append(min(1.0, raw / 0.25))
    if not margins:
        return 0.0
    return float(np.mean(margins))


def thumb_direction(landmarks: np.ndarray) -> Optional[tuple[float, float]]:
    """Normalized thumb direction (tip - ip) in image coordinates."""
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 21:
        return None
    vector = points[4, :2] - points[3, :2]
    norm = float(np.hypot(*vector))
    if norm < 1e-6:
        return None
    return float(vector[0] / norm), float(vector[1] / norm)


def palm_axis(landmarks: np.ndarray) -> Optional[tuple[float, float]]:
    """Normalized palm axis: wrist -> middle MCP (points 'up' the hand)."""
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 21:
        return None
    vector = points[9, :2] - points[0, :2]
    norm = float(np.hypot(*vector))
    if norm < 1e-6:
        return None
    return float(vector[0] / norm), float(vector[1] / norm)
