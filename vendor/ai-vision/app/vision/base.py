"""Base class and status model for vision pipeline modules.

A module encapsulates one analysis capability (face detection, face mesh,
later eye tracking, hands, ...). Modules are loaded lazily — importing
them must never import mediapipe, so the app stays usable when mediapipe
or the models are unavailable.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from app.core.types import VisionResult
from app.utils.logging_setup import get_logger

log = get_logger("vision.base")


class ModuleStatus(enum.Enum):
    """Lifecycle state of a vision module."""

    UNLOADED = "unloaded"   # models not loaded yet
    READY = "ready"         # models loaded, module can process frames
    ERROR = "error"         # model/initialisation failed, module is skipped


class VisionModule(ABC):
    """Base class for all vision analysis modules.

    Subclasses must define :attr:`key`, :attr:`display_name` and implement
    :meth:`load`, :meth:`process` and (optionally) :meth:`unload`.
    """

    key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.status = ModuleStatus.UNLOADED
        self.status_message = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load models/resources. Must set status READY or raise VisionError."""
        raise NotImplementedError

    def unload(self) -> None:
        """Release models/resources (default: nothing to release)."""

    def close(self) -> None:
        """Safely release everything; never raises."""
        try:
            if self.status is not ModuleStatus.UNLOADED:
                self.unload()
        except Exception:  # noqa: BLE001 — teardown must not crash
            log.exception("Error while unloading module %s", self.key)
        self.status = ModuleStatus.UNLOADED

    def _fail(self, message: str) -> None:
        """Record an error state (used by the pipeline after a failed load)."""
        self.status = ModuleStatus.ERROR
        self.status_message = message

    @property
    def is_ready(self) -> bool:
        return self.status is ModuleStatus.READY

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    @abstractmethod
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        """Analyse one BGR frame and write findings into ``result``.

        Must not raise in normal operation; unexpected exceptions are
        caught by the pipeline, logged, and the module keeps running.

        Args:
            frame: BGR frame (H x W x 3, uint8).
            result: Shared result object of the current pipeline pass.
        """
