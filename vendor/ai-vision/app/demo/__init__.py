"""Demo mode: simulated camera feed + scripted product run."""

from app.demo.frames import DemoCameraManager, DemoFrameSource
from app.demo.overlay import DemoOverlay
from app.demo.runner import DemoRunner, DemoStep

__all__ = [
    "DemoCameraManager",
    "DemoFrameSource",
    "DemoOverlay",
    "DemoRunner",
    "DemoStep",
]
