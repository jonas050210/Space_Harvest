"""Session video recorder + still snapshots (Phase 28).

Writes annotated (or raw) camera frames to a local file. Bounded by
duration and file size so a forgotten RECORD cannot fill the disk.
Thread-safe: ``write()`` is called from the capture worker.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.utils.logging_setup import get_logger

log = get_logger("capture.recorder")

#: Hard caps — a forgotten RECORD must not fill the disk.
DEFAULT_MAX_SECONDS = 10 * 60
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
_SNAPSHOT_QUALITY = [int(cv2.IMWRITE_JPEG_QUALITY), 92]


@dataclass(frozen=True)
class RecordingInfo:
    """Result of one finished recording (or a still snapshot)."""

    path: Path
    frames: int
    duration_s: float
    width: int
    height: int
    fps: float
    bytes: int
    reason: str  # "stopped" | "max-duration" | "max-size" | "snapshot" | "failed"


class SessionRecorder:
    """Local MJPG/MP4 writer with honest start/stop and hard bounds."""

    def __init__(
        self,
        directory: Path,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._directory = Path(directory)
        self._max_seconds = max(5.0, float(max_seconds))
        self._max_bytes = max(1_000_000, int(max_bytes))
        self._lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._path: Optional[Path] = None
        self._started_at = 0.0
        self._frames = 0
        self._width = 0
        self._height = 0
        self._fps = 30.0
        self._stop_reason = "stopped"

    # ------------------------------------------------------------------
    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._writer is not None

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._frames

    @property
    def elapsed_s(self) -> float:
        with self._lock:
            if self._writer is None:
                return 0.0
            return max(0.0, time.monotonic() - self._started_at)

    @property
    def path(self) -> Optional[Path]:
        with self._lock:
            return self._path

    def status(self) -> dict[str, object]:
        """Honest live status for the HUD / SYSTEM page."""
        with self._lock:
            if self._writer is None:
                return {"recording": False, "frames": 0, "elapsed_s": 0.0}
            return {
                "recording": True,
                "frames": self._frames,
                "elapsed_s": round(time.monotonic() - self._started_at, 1),
                "path": str(self._path) if self._path else "",
                "width": self._width,
                "height": self._height,
            }

    # ------------------------------------------------------------------
    def start(
        self,
        width: int,
        height: int,
        fps: float = 30.0,
        stem: Optional[str] = None,
    ) -> Path:
        """Open a writer. Raises RuntimeError if already recording."""
        if width < 16 or height < 16:
            raise RuntimeError("Cannot record: frame size is too small.")
        fps = float(fps) if fps and fps > 1.0 else 15.0
        fps = max(5.0, min(60.0, fps))
        self._directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = stem or f"recording_{stamp}"
        path, writer = _open_writer(self._directory / name, width, height, fps)
        if writer is None or not writer.isOpened():
            raise RuntimeError(
                "Could not open a video writer on this machine "
                "(no usable codec)."
            )
        with self._lock:
            if self._writer is not None:
                writer.release()
                raise RuntimeError("Already recording — stop first.")
            self._writer = writer
            self._path = path
            self._started_at = time.monotonic()
            self._frames = 0
            self._width = int(width)
            self._height = int(height)
            self._fps = fps
            self._stop_reason = "stopped"
        log.info("Recording started → %s (%dx%d @ %.1f fps)", path, width, height, fps)
        return path

    def write(self, frame: np.ndarray) -> Optional[RecordingInfo]:
        """Append one BGR frame. Returns RecordingInfo if auto-stopped."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        with self._lock:
            writer = self._writer
            if writer is None:
                return None
            try:
                if frame.shape[1] != self._width or frame.shape[0] != self._height:
                    frame = cv2.resize(frame, (self._width, self._height))
                writer.write(frame)
                self._frames += 1
            except Exception as exc:  # noqa: BLE001 — capture must not die
                log.warning("Recorder write failed: %s", exc)
                self._stop_reason = "failed"
                return self._stop_locked()
            elapsed = time.monotonic() - self._started_at
            size = _file_size(self._path)
            if elapsed >= self._max_seconds:
                self._stop_reason = "max-duration"
                return self._stop_locked()
            if size >= self._max_bytes:
                self._stop_reason = "max-size"
                return self._stop_locked()
            return None

    def stop(self, reason: str = "stopped") -> Optional[RecordingInfo]:
        """Close the writer. Idempotent — None if nothing was recording."""
        with self._lock:
            if self._writer is None:
                return None
            self._stop_reason = reason
            return self._stop_locked()

    def snapshot(self, frame: np.ndarray, stem: Optional[str] = None) -> Path:
        """Save one still as JPEG next to the recordings. Never raises."""
        if frame is None or getattr(frame, "size", 0) == 0:
            raise RuntimeError("No frame to snapshot.")
        self._directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = self._directory / f"{stem or 'snapshot_' + stamp}.jpg"
        ok, encoded = cv2.imencode(".jpg", frame, _SNAPSHOT_QUALITY)
        if not ok:
            raise RuntimeError("Could not encode the snapshot.")
        path.write_bytes(encoded.tobytes())
        log.info("Snapshot saved → %s", path)
        return path

    # ------------------------------------------------------------------
    def _stop_locked(self) -> Optional[RecordingInfo]:
        writer = self._writer
        path = self._path
        frames = self._frames
        duration = max(0.0, time.monotonic() - self._started_at)
        width, height, fps = self._width, self._height, self._fps
        reason = self._stop_reason
        self._writer = None
        self._path = None
        self._frames = 0
        if writer is not None:
            try:
                writer.release()
            except Exception:  # noqa: BLE001
                pass
        if path is None:
            return None
        info = RecordingInfo(
            path=path,
            frames=frames,
            duration_s=round(duration, 2),
            width=width,
            height=height,
            fps=fps,
            bytes=_file_size(path),
            reason=reason,
        )
        log.info(
            "Recording stopped (%s) → %s · %d frames · %.1fs",
            reason, path, frames, duration,
        )
        return info


def _open_writer(
    stem: Path, width: int, height: int, fps: float
) -> tuple[Path, Optional[cv2.VideoWriter]]:
    """Try MP4 then AVI/MJPG. Returns (path, writer-or-None)."""
    candidates = (
        (".mp4", "mp4v"),
        (".avi", "MJPG"),
        (".avi", "XVID"),
    )
    for suffix, fourcc_name in candidates:
        path = stem.with_suffix(suffix)
        fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
        if writer is not None and writer.isOpened():
            return path, writer
        if writer is not None:
            writer.release()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return stem.with_suffix(".mp4"), None


def _file_size(path: Optional[Path]) -> int:
    if path is None:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0
