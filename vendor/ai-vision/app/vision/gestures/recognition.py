"""Gesture recognition from finger states (geometric rules, no ML).

The module consumes the hands that HandTrackingModule already produced
(shared data, no extra inference) and classifies each hand into one of
eight gestures:

OPEN PALM, FIST, POINT, PEACE, THUMBS UP, THUMBS DOWN, OK, UNKNOWN.

Every gesture gets a geometric plausibility confidence (0..1); the module
only reports gestures whose confidence reaches the configured threshold,
so implausible readings are suppressed instead of asserted.
"""

from __future__ import annotations

import time

import numpy as np

from app.core.types import GestureResult, TrackedHand, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule
from app.vision.hands.geometry import (
    finger_state_margin,
    finger_states,
    hand_size,
    palm_axis,
    thumb_direction,
)

log = get_logger("vision.gestures.recognition")

#: All five finger names in canonical order.
_FINGERS = ("thumb", "index", "middle", "ring", "pinky")

#: Base confidence per gesture type (rule-specific plausibility).
_BASE_CONFIDENCE = {
    "OPEN PALM": 0.92,
    "FIST": 0.92,
    "POINT": 0.82,
    "PEACE": 0.80,
    "THUMBS UP": 0.78,
    "THUMBS DOWN": 0.78,
    "OK": 0.74,
    "UNKNOWN": 0.30,
}

#: OK gesture: thumb tip must be this close to the index tip (relative to
#: hand size) while the middle/ring/pinky stay extended.
_OK_TIP_DISTANCE = 0.22


def classify_hand(hand: TrackedHand) -> tuple[str, float]:
    """Classify one hand; returns (gesture, confidence 0..1).

    Pure geometry: finger states, thumb direction vs. palm axis, and tip
    proximity for OK. Never raises.
    """
    states = hand.finger_states or finger_states(hand.landmarks)
    up = {name for name, state in states.items() if state == "UP"}
    down = {name for name, state in states.items() if state == "DOWN"}
    decided = up | down

    # All fingers must be decided for a meaningful gesture.
    if len(decided) < 5:
        return "UNKNOWN", _BASE_CONFIDENCE["UNKNOWN"]

    size = hand_size(hand.landmarks)
    thumb_up = "thumb" in up
    index_up = "index" in up
    middle_up = "middle" in up
    ring_up = "ring" in up
    pinky_up = "pinky" in up

    gesture = "UNKNOWN"

    # OK: thumb tip touches index tip, other three fingers extended.
    if index_up and middle_up and ring_up and pinky_up:
        points = np.asarray(hand.landmarks, dtype=np.float32)
        tip_distance = float(np.hypot(*(points[4, :2] - points[8, :2])))
        if size > 0 and tip_distance <= _OK_TIP_DISTANCE * size:
            gesture = "OK"

    if gesture == "UNKNOWN" and thumb_up and not any(
        (index_up, middle_up, ring_up, pinky_up)
    ):
        # Thumb-only gestures: orientation decides up vs down.
        direction = thumb_direction(hand.landmarks)
        axis = palm_axis(hand.landmarks)
        if direction is not None and axis is not None:
            alignment = direction[0] * axis[0] + direction[1] * axis[1]
            gesture = "THUMBS UP" if alignment >= 0 else "THUMBS DOWN"
        else:
            gesture = "THUMBS UP"  # neutral fallback, low confidence below

    if gesture == "UNKNOWN" and index_up and not any(
        (middle_up, ring_up, pinky_up)
    ):
        gesture = "POINT"

    if gesture == "UNKNOWN" and index_up and middle_up and not any(
        (ring_up, pinky_up)
    ) and not thumb_up:
        gesture = "PEACE"

    if gesture == "UNKNOWN" and up == set(_FINGERS):
        gesture = "OPEN PALM"

    if gesture == "UNKNOWN" and down == set(_FINGERS):
        gesture = "FIST"

    # Confidence: rule plausibility x geometric decision margin x hand
    # detection confidence.
    margin = finger_state_margin(hand.landmarks, states)
    confidence = _BASE_CONFIDENCE[gesture] * (0.35 + 0.65 * margin)
    confidence *= max(0.2, min(1.0, hand.handedness_confidence or 0.9))
    if gesture in ("THUMBS UP", "THUMBS DOWN", "OK"):
        confidence *= 0.9  # orientation-sensitive rules are less certain
    return gesture, round(float(np.clip(confidence, 0.0, 1.0)), 3)


class GestureRecognitionModule(VisionModule):
    """Vision module: classifies each tracked hand's gesture.

    Args:
        confidence_threshold: Gestures below this confidence are not
            reported (suppressed instead of asserted).
    """

    key = "gesture_recognition"
    display_name = "Gesture Recognition"

    def __init__(
        self,
        enabled: bool = True,
        confidence_threshold: float = 0.5,
        clock=time.monotonic,
    ) -> None:
        super().__init__(enabled=enabled)
        self._confidence_threshold = confidence_threshold
        self._clock = clock

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_confidence_threshold(self, value: float) -> None:
        self._confidence_threshold = float(value)
        log.info(
            "Gesture confidence threshold set to %.2f", self._confidence_threshold
        )

    # ------------------------------------------------------------------
    def load(self) -> None:
        self.status_message = ""

    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        gestures: list[GestureResult] = []
        for hand in result.hands:
            try:
                gesture, confidence = classify_hand(hand)
            except Exception:  # noqa: BLE001 — bad hand data must not kill the frame
                log.exception("Gesture classification failed for hand %d", hand.id)
                continue
            if confidence < self._confidence_threshold:
                continue  # not plausible enough — do not assert anything
            gestures.append(
                GestureResult(
                    gesture=gesture,
                    confidence=confidence,
                    hand_id=hand.id,
                    handedness=hand.handedness,
                    timestamp=self._clock(),
                )
            )
        result.gestures = gestures
