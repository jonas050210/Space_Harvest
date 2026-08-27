"""Demo frame source and camera manager.

The demo mode runs the *real* vision pipeline (real MediaPipe models) on
a scripted frame stream built from bundled demo images — no hardware is
required and no values are faked. Every frame carries a visible
"DEMO FEED" watermark, and the UI shows a DEMO MODE overlay, so demo
data can never be mistaken for a real camera.

Phases (cycled): desk scene (objects) -> person (face/body/arms) ->
hand (gesture) -> fist. A slow synthetic pan within each phase produces
real landmark movement for the movement tracker.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.camera.camera_manager import CameraInfo, CameraManager
from app.utils.paths import PROJECT_ROOT

#: Demo phases: (image asset, duration in frames, pan pixels per frame).
_PHASES = (
    ("desk.jpg", 90, (0, 0)),
    ("person.jpg", 110, (2, 0)),
    ("hand.jpg", 80, (1, 1)),
    ("fist.jpg", 60, (0, 0)),
)

#: Default output resolution of the demo feed (keeps the pipeline fast).
_DEMO_SIZE = (960, 540)


def _load_demo_images() -> list[np.ndarray]:
    """Load the bundled demo images (assets/demo, packaged with the app)."""
    images: list[np.ndarray] = []
    for asset, _frames, _pan in _PHASES:
        for base in (
            PROJECT_ROOT / "assets" / "demo",
            PROJECT_ROOT / "tests" / "data",
        ):
            path = base / asset
            if path.exists():
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is not None:
                    images.append(image)
                    break
        else:
            raise FileNotFoundError(f"Demo asset missing: {asset}")
    return images


class DemoFrameSource:
    """cv2.VideoCapture-compatible demo frame stream."""

    def __init__(self, index: int = 0, size: tuple[int, int] = _DEMO_SIZE) -> None:
        self.index = index
        self.props: dict[int, float] = {}
        self.released = False
        self._images = _load_demo_images()
        self._target_w, self._target_h = size
        self._phase = 0
        self._frame_in_phase = 0

    # ------------------------------------------------------------------
    def isOpened(self) -> bool:  # noqa: N802 — cv2 API
        return not self.released

    def read(self) -> tuple[bool, np.ndarray]:
        if self.released:
            return False, None
        asset, phase_frames, pan = _PHASES[self._phase]
        image = self._images[self._phase]

        # Slow synthetic pan -> real landmark movement.
        t = self._frame_in_phase / max(1, phase_frames - 1)
        shift_x = int(pan[0] * t * phase_frames)
        shift_y = int(pan[1] * t * phase_frames)
        matrix = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
        panned = cv2.warpAffine(
            image, matrix, (image.shape[1], image.shape[0]),
            borderMode=cv2.BORDER_REPLICATE,
        )

        # Resize to the demo resolution + mild sensor noise.
        resized = cv2.resize(panned, (self._target_w, self._target_h))
        noise = np.random.randint(0, 4, resized.shape, dtype=np.uint8)
        frame = cv2.add(resized, noise)

        # Visible demo watermark (never mistaken for a real camera feed).
        cv2.rectangle(frame, (8, self._target_h - 34),
                      (170, self._target_h - 6), (20, 20, 40), -1)
        cv2.putText(frame, "DEMO FEED", (16, self._target_h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 1,
                    cv2.LINE_AA)

        self._frame_in_phase += 1
        if self._frame_in_phase >= phase_frames:
            self._frame_in_phase = 0
            self._phase = (self._phase + 1) % len(_PHASES)
        return True, frame

    def set(self, prop: int, value: float) -> None:
        self.props[prop] = value

    def release(self) -> None:
        self.released = True


class DemoCameraManager(CameraManager):
    """CameraManager presenting the demo feed as camera index 0."""

    def __init__(self, size: tuple[int, int] = _DEMO_SIZE) -> None:
        super().__init__(max_index=0)
        self._size = size

    def discover(self) -> list[CameraInfo]:
        return [
            CameraInfo(
                index=0,
                name="Demo Camera (simulated)",
                resolutions=[self._size],
            )
        ]

    def probe_resolutions(self, index: int) -> list[tuple[int, int]]:
        return [self._size]
