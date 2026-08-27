"""Calibration profile: model, prediction and local storage.

The profile maps gaze features ``[iris_h, iris_v, yaw_deg, pitch_deg]`` to
normalized video-area coordinates (0..1) via an affine (linear + bias)
regression fitted during calibration. Storage follows the same pattern as
the settings: JSON in the project data directory, validated on load,
atomic write, tolerant of corrupt files.

Local only — nothing is uploaded, no camera images are stored.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from app.utils.logging_setup import get_logger

log = get_logger("config.calibration")

CALIBRATION_VERSION = 1
FEATURE_DIM = 4  # [iris_h, iris_v, yaw_deg, pitch_deg]

#: Validity window: features may deviate this many standard deviations
#: from the calibration mean before the mapping is considered out-of-range.
_BOUNDS_SIGMA = 3.0


@dataclass
class CalibrationProfile:
    """Persisted gaze calibration mapping."""

    version: int = CALIBRATION_VERSION
    created_at: float = 0.0
    screen_width: int = 0   # video-area size at calibration time
    screen_height: int = 0
    quality: str = "poor"   # excellent | good | fair | poor
    mean_residual: float = 0.0  # normalized mean residual of the fit
    valid_points: int = 0
    total_points: int = 9
    coeff_x: list[float] = field(default_factory=lambda: [0.0] * (FEATURE_DIM + 1))
    coeff_y: list[float] = field(default_factory=lambda: [0.0] * (FEATURE_DIM + 1))
    center: list[float] = field(default_factory=lambda: [0.0] * FEATURE_DIM)
    scale: list[float] = field(default_factory=lambda: [1.0] * FEATURE_DIM)

    # ------------------------------------------------------------------
    def predict(self, features: Sequence[float]) -> tuple[float, float, bool]:
        """Map features to normalized (x, y); returns (x, y, within_bounds)."""
        vector = np.array(
            [float(f) for f in features] + [1.0], dtype=np.float64
        )
        x = float(np.dot(vector, np.asarray(self.coeff_x, dtype=np.float64)))
        y = float(np.dot(vector, np.asarray(self.coeff_y, dtype=np.float64)))
        x = float(np.clip(x, 0.0, 1.0))
        y = float(np.clip(y, 0.0, 1.0))

        within = True
        center = np.asarray(self.center, dtype=np.float64)
        scale = np.asarray(self.scale, dtype=np.float64)
        for i, value in enumerate(features[:FEATURE_DIM]):
            if scale[i] <= 1e-9:
                continue
            if abs(float(value) - center[i]) > _BOUNDS_SIGMA * scale[i]:
                within = False
                break
        return x, y, within

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Optional["CalibrationProfile"]:
        """Validated construction; returns None if the data is unusable."""
        try:
            if raw.get("version") != CALIBRATION_VERSION:
                log.warning("Calibration profile version mismatch — ignoring")
                return None
            coeff_x = _finite_list(raw.get("coeff_x"), FEATURE_DIM + 1)
            coeff_y = _finite_list(raw.get("coeff_y"), FEATURE_DIM + 1)
            center = _finite_list(raw.get("center"), FEATURE_DIM)
            scale = _finite_list(raw.get("scale"), FEATURE_DIM)
            if None in (coeff_x, coeff_y, center, scale):
                return None
            quality = str(raw.get("quality", "poor"))
            if quality not in {"excellent", "good", "fair", "poor"}:
                quality = "poor"
            return cls(
                version=CALIBRATION_VERSION,
                created_at=float(raw.get("created_at", 0.0)),
                screen_width=int(raw.get("screen_width", 0)),
                screen_height=int(raw.get("screen_height", 0)),
                quality=quality,
                mean_residual=float(raw.get("mean_residual", 0.0)),
                valid_points=int(raw.get("valid_points", 0)),
                total_points=int(raw.get("total_points", 9)),
                coeff_x=coeff_x,
                coeff_y=coeff_y,
                center=center,
                scale=scale,
            )
        except (TypeError, ValueError) as exc:
            log.warning("Invalid calibration profile: %s — ignoring", exc)
            return None


def _finite_list(value: Any, length: int) -> Optional[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    try:
        numbers = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in numbers):
        return None
    return numbers


class CalibrationStore:
    """Loads, saves and resets the calibration profile (JSON, local)."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._profile: Optional[CalibrationProfile] = None
        self._profile = self.load()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def profile(self) -> Optional[CalibrationProfile]:
        return self._profile

    def load(self) -> Optional[CalibrationProfile]:
        """Read the profile from disk; missing/corrupt -> None."""
        if not self._path.exists():
            log.info("No calibration profile at %s", self._path)
            self._profile = None
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read calibration profile %s: %s", self._path, exc)
            self._profile = None
            return None
        if not isinstance(raw, dict):
            self._profile = None
            return None
        profile = CalibrationProfile.from_dict(raw)
        self._profile = profile
        if profile is not None:
            log.info(
                "Calibration profile loaded (%s, %d/%d points)",
                profile.quality,
                profile.valid_points,
                profile.total_points,
            )
        return profile

    def save(self, profile: CalibrationProfile) -> None:
        """Persist a profile atomically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(profile.to_dict(), indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".calibration-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_path, self._path)
        except OSError as exc:
            log.error("Could not save calibration profile: %s", exc)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return
        self._profile = profile
        log.info(
            "Calibration profile saved (%s, %d/%d points)",
            profile.quality,
            profile.valid_points,
            profile.total_points,
        )

    def reset(self) -> None:
        """Delete the stored profile and clear the in-memory state."""
        self._profile = None
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not delete calibration profile: %s", exc)
        log.info("Calibration profile reset")
