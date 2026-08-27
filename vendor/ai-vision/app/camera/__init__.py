"""Camera subsystem: device discovery and frame capture engine."""

from app.camera.camera_engine import CameraEngine, FrameCallback, ErrorCallback
from app.camera.camera_manager import COMMON_RESOLUTIONS, CameraInfo, CameraManager

__all__ = [
    "CameraEngine",
    "FrameCallback",
    "ErrorCallback",
    "CameraInfo",
    "CameraManager",
    "COMMON_RESOLUTIONS",
]
