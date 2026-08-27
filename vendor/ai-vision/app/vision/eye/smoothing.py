"""Gaze smoothing: One-Euro filter (Casiez et al., CHI 2012).

The One-Euro filter adapts its cutoff to the signal speed, which keeps lag
low during fast movements while still removing jitter when the gaze rests.
The user can choose between three presets (LOW/MEDIUM/HIGH) at runtime.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

#: (min_cutoff, beta) presets — LOW = light filtering (responsive),
#: HIGH = strong filtering. Note: a *lower* One-Euro cutoff means more
#: smoothing; the presets map user expectation to the right parameters.
_PRESETS: dict[str, tuple[float, float]] = {
    "low": (2.5, 0.10),
    "medium": (1.2, 0.05),
    "high": (0.5, 0.02),
}
_DEFAULT_STRENGTH = "medium"


class OneEuroFilter:
    """One-Euro low-pass filter for a single scalar signal.

    Args:
        t0: Initial timestamp.
        x0: Initial value.
        min_cutoff: Minimum cutoff frequency (Hz) — higher = smoother.
        beta: Speed coefficient — higher = less smoothing during motion.
        d_cutoff: Cutoff for the derivative filter (fixed 1.0 is standard).
    """

    def __init__(
        self,
        t0: float,
        x0: float,
        min_cutoff: float = 2.0,
        beta: float = 0.08,
        d_cutoff: float = 1.0,
    ) -> None:
        if min_cutoff <= 0 or beta < 0 or d_cutoff <= 0:
            raise ValueError("Invalid One-Euro parameters")
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._prev_x = float(x0)
        self._prev_dx = 0.0
        self._prev_t = float(t0)

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        dt = t - self._prev_t
        if dt <= 0.0:
            # No (or negative) time step: hold the previous value.
            return self._prev_x
        if dt > 1.0:
            # Long pause (e.g. camera restart): avoid derivative spikes.
            dt = 1.0

        dx = (x - self._prev_x) / dt
        alpha_d = self._alpha(self._d_cutoff, dt)
        dx_hat = alpha_d * dx + (1.0 - alpha_d) * self._prev_dx

        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        alpha = self._alpha(cutoff, dt)
        x_hat = alpha * x + (1.0 - alpha) * self._prev_x

        self._prev_x = x_hat
        self._prev_dx = dx_hat
        self._prev_t = t
        return x_hat

    def reset(self, x0: float, t0: float) -> None:
        self._prev_x = float(x0)
        self._prev_dx = 0.0
        self._prev_t = float(t0)


class GazeSmoother:
    """Smoothes 2-D gaze points with two independent One-Euro filters."""

    def __init__(
        self,
        strength: str = _DEFAULT_STRENGTH,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._filters: Optional[tuple[OneEuroFilter, OneEuroFilter]] = None
        self._initialized = False
        self.set_strength(strength)

    def set_strength(self, strength: str) -> None:
        """Switch the smoothing preset (rebuilds the filters)."""
        if strength not in _PRESETS:
            strength = _DEFAULT_STRENGTH
        self._strength = strength
        min_cutoff, beta = _PRESETS[strength]
        t0 = self._clock()
        self._filters = (
            OneEuroFilter(t0, 0.5, min_cutoff=min_cutoff, beta=beta),
            OneEuroFilter(t0, 0.5, min_cutoff=min_cutoff, beta=beta),
        )
        self._initialized = False

    @property
    def strength(self) -> str:
        return self._strength

    def smooth(self, x: float, y: float, t: Optional[float] = None) -> tuple[float, float]:
        """Filter one gaze point; returns the smoothed (x, y)."""
        assert self._filters is not None
        now = self._clock() if t is None else t
        if not self._initialized:
            self._filters[0].reset(x, now)
            self._filters[1].reset(y, now)
            self._initialized = True
        return self._filters[0](x, now), self._filters[1](y, now)

    def reset(self) -> None:
        """Forget the filter state (new camera session)."""
        self.set_strength(self._strength)
