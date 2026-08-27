"""Stable object tracking across frames (centroid matching + grace period).

Simple and deterministic: detections are matched to existing tracks by
centroid distance (relative to the frame diagonal). A matched object keeps
its ID even when its class label flips (the label is updated); a track
survives a few frames of absence, so short occlusions do not produce new
IDs. No heavy appearance model — quality and simple architecture over
complexity.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from app.core.types import Box, ObjectDetection, TrackedObject


class _ObjectTrack:
    __slots__ = ("object_id", "last_box", "class_name", "confidence",
                 "last_center", "velocity", "missing")

    def __init__(self, object_id: int, box: Box, class_name: str, confidence: float) -> None:
        self.object_id = object_id
        self.last_box = box
        self.class_name = class_name
        self.confidence = confidence
        self.last_center: Optional[tuple[float, float]] = None
        self.velocity: Optional[float] = None
        self.missing = 0

    def hit(self, box: Box, class_name: str, confidence: float) -> None:
        self.last_center = self.last_box.centroid()
        self.last_box = box
        self.velocity = math.hypot(
            box.centroid()[0] - self.last_center[0],
            box.centroid()[1] - self.last_center[1],
        )
        # Keep the ID even if the class label flips — the physical object
        # did not change.
        if class_name:
            self.class_name = class_name
        if confidence is not None:
            self.confidence = confidence
        self.missing = 0

    def miss(self) -> None:
        self.missing += 1


class ObjectTracker:
    """Assigns stable IDs to object detections.

    Args:
        max_shift_ratio: Maximum centroid movement between frames as a
            fraction of the frame diagonal (0.3 = 30%).
        max_missing_frames: Frames an object may be absent before its
            track is dropped.
    """

    def __init__(
        self,
        max_shift_ratio: float = 0.30,
        max_missing_frames: int = 8,
    ) -> None:
        if not 0.0 < max_shift_ratio <= 1.0:
            raise ValueError("max_shift_ratio must be in (0, 1]")
        if max_missing_frames < 0:
            raise ValueError("max_missing_frames must be >= 0")
        self._max_shift_ratio = max_shift_ratio
        self._max_missing_frames = max_missing_frames
        self._tracks: dict[int, _ObjectTrack] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(
        self,
        detections: Sequence[ObjectDetection],
        frame_width: int,
        frame_height: int,
    ) -> list[TrackedObject]:
        """Feed one frame's detections; returns the visible tracked objects."""
        diagonal = max(1.0, math.hypot(frame_width, frame_height))
        max_distance = self._max_shift_ratio * diagonal

        visible: list[TrackedObject] = []
        unmatched = list(detections)
        for track in self._tracks.values():
            if not unmatched:
                track.miss()
                continue
            best_index: Optional[int] = None
            best_distance = float("inf")
            for i, detection in enumerate(unmatched):
                cx, cy = detection.bbox.centroid()
                lx, ly = track.last_box.centroid()
                distance = math.hypot(cx - lx, cy - ly)
                if distance < best_distance:
                    best_distance = distance
                    best_index = i
            if best_index is not None and best_distance <= max_distance:
                detection = unmatched.pop(best_index)
                track.hit(detection.bbox, detection.class_name, detection.confidence)
                visible.append(self._to_tracked(track))
            else:
                track.miss()

        for detection in unmatched:
            self._tracks[self._next_id] = _ObjectTrack(
                self._next_id, detection.bbox, detection.class_name, detection.confidence
            )
            visible.append(self._to_tracked(self._tracks[self._next_id]))
            self._next_id += 1

        for object_id in [
            oid for oid, t in self._tracks.items() if t.missing > self._max_missing_frames
        ]:
            del self._tracks[object_id]

        return sorted(visible, key=lambda obj: obj.id)

    @staticmethod
    def _to_tracked(track: _ObjectTrack) -> TrackedObject:
        return TrackedObject(
            id=track.object_id,
            class_name=track.class_name,
            confidence=round(track.confidence, 4),
            bbox=track.last_box,
            tracking_state="tracked",
            velocity=(
                round(track.velocity, 2) if track.velocity is not None else None
            ),
        )
