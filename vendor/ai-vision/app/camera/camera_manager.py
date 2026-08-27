"""Camera device discovery and resolution probing.

Discovery briefly opens each candidate index, reads one frame to confirm
the device actually delivers images, and closes it again. Resolution
probing opens the selected device once and tests a small list of common
resolutions. Both operations only run on explicit user/startup request —
the engine itself opens the camera exactly once per start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2

from app.utils.logging_setup import get_logger

log = get_logger("camera.manager")

#: Resolutions offered in the UI (probed per camera, kept if supported).
COMMON_RESOLUTIONS: tuple[tuple[int, int], ...] = (
    (2560, 1440),   # 2K QHD webcams (e.g. AirHug 02) — MJPG codec
    (1920, 1080),
    (1280, 720),
    (960, 540),
    (640, 480),
    (640, 360),
)

DEFAULT_RESOLUTION = (640, 480)


@dataclass
class CameraInfo:
    """A discovered camera device with its supported resolutions."""

    index: int
    name: str
    resolutions: list[tuple[int, int]] = field(default_factory=list)


class CameraManager:
    """Detects cameras and probes their capabilities.

    Args:
        max_index: Highest device index to probe during discovery.
    """

    def __init__(self, max_index: int = 6) -> None:
        self._max_index = max_index

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def discover(self) -> list[CameraInfo]:
        """Return all cameras that actually deliver a frame. Empty if none.

        Each candidate index is opened, read once and closed again.
        """
        found: list[CameraInfo] = []
        for index in range(self._max_index + 1):
            capture = cv2.VideoCapture(index)
            try:
                if not capture.isOpened():
                    continue
                ok, _ = capture.read()
                if not ok:
                    continue
                name = f"Camera {index}"
                found.append(CameraInfo(index=index, name=name))
                log.info("Camera found: index %d", index)
            finally:
                capture.release()
        if not found:
            log.warning("No camera detected")
        return found

    # ------------------------------------------------------------------
    # Resolution probing
    # ------------------------------------------------------------------
    def probe_resolutions(self, index: int) -> list[tuple[int, int]]:
        """Probe which common resolutions the given camera supports.

        Opens the camera once, tries each candidate and keeps the ones the
        driver accepts (verified with a real frame read).
        """
        capture = cv2.VideoCapture(index)
        if not capture.isOpened():
            log.warning("Cannot probe resolutions: camera %d not openable", index)
            return [DEFAULT_RESOLUTION]
        try:
            supported: list[tuple[int, int]] = []
            for width, height in COMMON_RESOLUTIONS:
                if self._try_resolution(capture, width, height):
                    if (width, height) not in supported:
                        supported.append((width, height))
            if not supported:
                supported.append(DEFAULT_RESOLUTION)
            log.info(
                "Camera %d supports resolutions: %s",
                index,
                ", ".join(f"{w}x{h}" for w, h in supported),
            )
            return supported
        finally:
            capture.release()

    @staticmethod
    def _try_resolution(capture: "cv2.VideoCapture", width: int, height: int) -> bool:
        """Attempt to set a resolution and verify it with a real read."""
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, frame = capture.read()
        if not ok or frame is None:
            return False
        actual_h, actual_w = frame.shape[:2]
        # Drivers often round to the nearest supported mode; accept close matches.
        return abs(actual_w - width) <= 16 and abs(actual_h - height) <= 16

    @staticmethod
    def resolution_label(resolution: tuple[int, int] | str | None) -> str:
        """Human-readable resolution label, e.g. ``1280 x 720``."""
        if resolution is None:
            return "—"
        if isinstance(resolution, str):
            parts = resolution.lower().replace(" ", "").split("x")
            if len(parts) == 2 and all(part.isdigit() for part in parts):
                return f"{parts[0]} × {parts[1]}"
            return resolution
        width, height = resolution
        return f"{width} × {height}"

    @staticmethod
    def parse_resolution(text: str) -> tuple[int, int]:
        """Parse a ``WxH`` string into a pixel tuple; raises ValueError."""
        parts = text.lower().replace(" ", "").split("x")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid resolution format: {text!r}")
        return int(parts[0]), int(parts[1])

    @staticmethod
    def find_closest(
        desired: tuple[int, int], available: list[tuple[int, int]]
    ) -> Optional[tuple[int, int]]:
        """Return the available resolution closest to the desired one."""
        if not available:
            return None
        desired_area = desired[0] * desired[1]
        return min(
            available,
            key=lambda res: abs(res[0] * res[1] - desired_area),
        )
