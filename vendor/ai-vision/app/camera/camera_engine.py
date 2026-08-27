"""Camera capture engine.

Owns exactly one ``cv2.VideoCapture`` for its lifetime and runs a single
daemon capture thread. The camera is opened once per :meth:`start`, is
never re-opened while running, and is guaranteed to be released on
:meth:`stop` (also on thread errors). Frames are pushed to a callback;
errors are reported via a separate callback and terminate the loop.

The engine is UI-framework agnostic (no Qt imports), which keeps it fully
unit-testable with a mocked ``cv2.VideoCapture``.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import cv2
import numpy as np

from app.core.errors import CameraDisconnectedError, CameraOpenError
from app.utils.logging_setup import get_logger

log = get_logger("camera.engine")

FrameCallback = Callable[[np.ndarray], None]
ErrorCallback = Callable[[Exception], None]


class CameraEngine:
    """Threaded capture loop for a single camera device.

    Args:
        on_frame: Called with every successfully read BGR frame
            (from the capture thread).
        on_error: Called with the exception when the camera fails
            irrecoverably (from the capture thread).
        max_read_failures: Consecutive failed reads that count as a
            disconnection (individual dropped frames are tolerated).
        capture_factory: Callable(index) -> capture object; defaults to
            ``cv2.VideoCapture``. Injectable for tests and for the demo
            mode's simulated feed (the engine logic stays identical).
    """

    def __init__(
        self,
        on_frame: FrameCallback,
        on_error: ErrorCallback,
        max_read_failures: int = 10,
        capture_factory: Optional[Callable[[int], object]] = None,
    ) -> None:
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._on_frame = on_frame
        self._on_error = on_error
        self._max_read_failures = max_read_failures

        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._index: Optional[int] = None
        self._requested_size: tuple[int, int] = (0, 0)
        self._actual_size: tuple[int, int] = (0, 0)
        self._fps_target: int = 30
        self._first_frame: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """True while the capture thread is alive."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def index(self) -> Optional[int]:
        return self._index

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Resolution the driver actually delivers (0, 0 while stopped)."""
        return self._actual_size

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(
        self,
        index: int,
        width: int,
        height: int,
        fps_target: int = 30,
    ) -> None:
        """Open the camera and start the capture thread.

        Raises:
            CameraOpenError: If the device cannot be opened or delivers no frame.
            RuntimeError: If the engine is already running.
        """
        if self.is_running:
            raise RuntimeError("Camera engine is already running")
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid resolution: {width}x{height}")

        with self._lock:
            capture = self._capture_factory(index)
            # 2K webcams (e.g. AirHug 02) only deliver 2560x1440 over the
            # MJPG codec. Request MJPG FIRST (before the resolution): if
            # the driver accepts it, 2K works; if not, the request is
            # harmlessly ignored and YUYV keeps working up to 1080p.
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_FPS, fps_target)

            if not capture.isOpened():
                capture.release()
                raise CameraOpenError(
                    f"Camera {index} could not be opened "
                    "(in use by another application, unplugged, or driver issue)."
                )

            ok, first_frame = capture.read()
            if not ok or first_frame is None:
                capture.release()
                raise CameraOpenError(
                    f"Camera {index} opened but delivered no frame."
                )

            actual_h, actual_w = first_frame.shape[:2]
            self._capture = capture
            self._index = index
            self._requested_size = (width, height)
            self._actual_size = (actual_w, actual_h)
            self._fps_target = fps_target
            self._first_frame = first_frame
            self._stop_event.clear()

        log.info(
            "Camera %d started: requested %dx%d @ %d fps, actual %dx%d",
            index, width, height, fps_target, actual_w, actual_h,
        )

        self._thread = threading.Thread(
            target=self._capture_loop,
            name="camera-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the capture thread and release the camera. Idempotent."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        with self._lock:
            capture, self._capture = self._capture, None
            if capture is not None:
                capture.release()
        self._thread = None
        self._index = None
        self._actual_size = (0, 0)
        self._first_frame = None
        log.info("Camera stopped and released")

    # ------------------------------------------------------------------
    # Capture loop (worker thread)
    # ------------------------------------------------------------------
    def _capture_loop(self) -> None:
        consecutive_failures = 0
        try:
            while not self._stop_event.is_set():
                # Deliver the frame read during start() first — inside the
                # loop so consumer errors follow the normal error path.
                with self._lock:
                    frame = self._first_frame
                    self._first_frame = None
                    capture = self._capture
                if frame is not None:
                    self._on_frame(frame)
                    continue
                if capture is None:
                    break
                ok, frame = capture.read()
                if ok and frame is not None:
                    consecutive_failures = 0
                    self._on_frame(frame)
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= self._max_read_failures:
                        log.error(
                            "Camera lost after %d consecutive failed reads",
                            consecutive_failures,
                        )
                        self._on_error(
                            CameraDisconnectedError(
                                "Camera connection lost. The device was unplugged "
                                "or grabbed by another application."
                            )
                        )
                        break
                    self._stop_event.wait(0.01)
        except Exception as exc:  # noqa: BLE001 — protect the thread
            log.exception("Unexpected error in capture loop")
            self._on_error(CameraDisconnectedError(f"Camera failed: {exc}"))
        finally:
            # Guarantee resource release even on unexpected failure.
            with self._lock:
                capture, self._capture = self._capture, None
            if capture is not None:
                capture.release()
            log.info("Capture thread ended")
