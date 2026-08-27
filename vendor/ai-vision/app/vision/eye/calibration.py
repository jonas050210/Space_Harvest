"""Gaze calibration: sample collection and regression fitting.

The calibration procedure shows N target points (default 3x3 grid) on the
video area while the user looks at them. For each point the current gaze
features ``[iris_h, iris_v, yaw_deg, pitch_deg]`` are collected (several
samples, then averaged). An affine regression maps features -> normalized
screen coordinates. Quality is derived from the fit residual — explicitly
no medical or sub-degree accuracy claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from app.config.calibration import CalibrationProfile
from app.utils.logging_setup import get_logger

log = get_logger("vision.eye.calibration")

#: Default calibration targets: 3x3 grid in normalized video coordinates
#: (15% margin so the dots stay comfortably inside the video area).
DEFAULT_TARGETS: tuple[tuple[float, float], ...] = tuple(
    (x, y)
    for y in (0.15, 0.5, 0.85)
    for x in (0.15, 0.5, 0.85)
)

#: Minimum number of valid samples per point.
MIN_SAMPLES_PER_POINT = 5
#: Minimum number of valid points for a usable calibration.
MIN_VALID_POINTS = 5

#: Quality thresholds on the normalized mean residual (fraction of the
#: video-area diagonal).
_EXCELLENT = 0.03
_GOOD = 0.06
_FAIR = 0.10


@dataclass
class CalibrationPoint:
    """Collected data for one target point."""

    target: tuple[float, float]
    samples: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def mean_features(self) -> Optional[np.ndarray]:
        if len(self.samples) < MIN_SAMPLES_PER_POINT:
            return None
        array = np.asarray(self.samples, dtype=np.float64)
        return array.mean(axis=0)


def rating_for_residual(residual: float) -> str:
    """Qualitative rating of the normalized mean residual."""
    if residual <= _EXCELLENT:
        return "excellent"
    if residual <= _GOOD:
        return "good"
    if residual <= _FAIR:
        return "fair"
    return "poor"


def fit_calibration(
    points: Sequence[CalibrationPoint],
    screen_width: int = 0,
    screen_height: int = 0,
    created_at: float = 0.0,
) -> Optional[CalibrationProfile]:
    """Fit an affine feature->screen mapping from the collected points.

    Returns None if there is not enough valid data (the user was not
    visible long enough). Never raises.
    """
    valid = [p for p in points if p.mean_features is not None]
    if len(valid) < MIN_VALID_POINTS:
        log.warning(
            "Calibration failed: %d valid points (need %d)",
            len(valid),
            MIN_VALID_POINTS,
        )
        return None

    features = np.stack([p.mean_features for p in valid])  # (M, 4)
    targets = np.asarray([p.target for p in valid], dtype=np.float64)  # (M, 2)

    design = np.hstack([features, np.ones((len(valid), 1))])  # (M, 5)
    try:
        coeff_x, *_ = np.linalg.lstsq(design, targets[:, 0], rcond=None)
        coeff_y, *_ = np.linalg.lstsq(design, targets[:, 1], rcond=None)
    except np.linalg.LinAlgError as exc:  # noqa: BLE001 — degenerate data
        log.error("Calibration regression failed: %s", exc)
        return None

    # Residual of the fit on the calibration data itself.
    predicted = design @ np.column_stack([coeff_x, coeff_y])
    residuals = np.linalg.norm(predicted - targets, axis=1)
    mean_residual = float(residuals.mean() / np.sqrt(2.0))  # normalized

    center = features.mean(axis=0)
    scale = features.std(axis=0)
    scale = np.where(scale < 1e-6, 1.0, scale)

    profile = CalibrationProfile(
        created_at=created_at,
        screen_width=int(screen_width),
        screen_height=int(screen_height),
        quality=rating_for_residual(mean_residual),
        mean_residual=round(mean_residual, 5),
        valid_points=len(valid),
        total_points=len(points),
        coeff_x=[float(v) for v in coeff_x],
        coeff_y=[float(v) for v in coeff_y],
        center=[float(v) for v in center],
        scale=[float(v) for v in scale],
    )
    log.info(
        "Calibration fitted: %s (residual %.4f, %d/%d points)",
        profile.quality,
        mean_residual,
        profile.valid_points,
        profile.total_points,
    )
    return profile

