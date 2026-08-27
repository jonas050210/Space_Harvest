"""Stable hand tracking across frames (handedness-aware centroid match)."""

from __future__ import annotations

import math
from typing import Optional, Sequence

from app.core.types import Box, TrackedHand


class _HandTrack:
    __slots__ = ("hand_id", "handedness", "last_bbox", "missing")

    def __init__(self, hand_id: int, handedness: str, bbox: Box) -> None:
        self.hand_id = hand_id
        self.handedness = handedness
        self.last_bbox = bbox
        self.missing = 0

    def hit(self, bbox: Box, handedness: str) -> None:
        self.last_bbox = bbox
        if handedness:
            self.handedness = handedness
        self.missing = 0

    def miss(self) -> None:
        self.missing += 1


class HandTracker:
    """Assigns stable IDs to hands.

    Matching requires both proximity *and* the same handedness, which
    keeps LEFT/RIGHT from swapping IDs when hands cross each other.
    """

    def __init__(
        self,
        max_shift_ratio: float = 0.45,
        max_missing_frames: int = 8,
    ) -> None:
        if not 0.0 < max_shift_ratio <= 1.0:
            raise ValueError("max_shift_ratio must be in (0, 1]")
        self._max_shift_ratio = max_shift_ratio
        self._max_missing_frames = max_missing_frames
        self._tracks: dict[int, _HandTrack] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(
        self,
        hands: Sequence[TrackedHand],
        frame_width: int,
        frame_height: int,
    ) -> list[TrackedHand]:
        """Feed one frame's hands; returns the visible ones with stable IDs."""
        diagonal = max(1.0, math.hypot(frame_width, frame_height))
        max_distance = self._max_shift_ratio * diagonal

        visible: list[TrackedHand] = []
        unmatched = list(hands)
        for track in self._tracks.values():
            if not unmatched:
                track.miss()
                continue
            best_index: Optional[int] = None
            best_distance = float("inf")
            for i, hand in enumerate(unmatched):
                if hand.handedness and track.handedness and hand.handedness != track.handedness:
                    continue  # never swap LEFT/RIGHT
                cx, cy = hand.bbox.centroid()
                lx, ly = track.last_bbox.centroid()
                distance = math.hypot(cx - lx, cy - ly)
                if distance < best_distance:
                    best_distance = distance
                    best_index = i
            if best_index is not None and best_distance <= max_distance:
                hand = unmatched.pop(best_index)
                track.hit(hand.bbox, hand.handedness)
                hand.id = track.hand_id
                hand.tracking_state = "tracked"
                visible.append(hand)
            else:
                track.miss()

        for hand in unmatched:
            hand.id = self._next_id
            hand.tracking_state = "tracked"
            self._tracks[self._next_id] = _HandTrack(
                self._next_id, hand.handedness, hand.bbox
            )
            visible.append(hand)
            self._next_id += 1

        for hand_id in [
            hid for hid, t in self._tracks.items() if t.missing > self._max_missing_frames
        ]:
            del self._tracks[hand_id]

        return sorted(visible, key=lambda hand: hand.id)
