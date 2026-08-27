"""Typed exceptions for AI Vision Lab.

Every subsystem raises one of these, so the UI layer can translate
technical failures into user-friendly messages while the log keeps
the technical details.
"""

from __future__ import annotations


class VisionLabError(Exception):
    """Base class for all application errors."""


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
class CameraError(VisionLabError):
    """Base class for camera-related errors."""


class CameraNotFoundError(CameraError):
    """No camera device could be discovered on this system."""


class CameraOpenError(CameraError):
    """A discovered camera exists but could not be opened/initialised."""


class CameraDisconnectedError(CameraError):
    """The camera stopped delivering frames while running."""


# --------------------------------------------------------------------------
# Vision
# --------------------------------------------------------------------------
class VisionError(VisionLabError):
    """Base class for vision subsystem errors."""


class ModelLoadError(VisionError):
    """A vision model could not be loaded (missing file, corrupt, or
    unsupported library version)."""


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
class ConfigError(VisionLabError):
    """The configuration file is invalid or unreadable."""
