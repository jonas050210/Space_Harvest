"""Blink detection (EAR-based state machine with temporal debounce)."""

from app.vision.blink.detector import BlinkDetectorModule, BlinkState

__all__ = ["BlinkDetectorModule", "BlinkState"]
