"""Stable face ID tracking across frames.

Matches detected boxes between consecutive frames by centroid distance
(relative to the frame diagonal). New boxes get new monotonically
increasing IDs; boxes that disappear are kept for a few frames and then
dropped. The tracker is independent of any detection library and therefore
fully unit-testable.
"""

from __future__ import annotations

import math
from typing import Sequence

from app.core.types import FaceBox, TrackedFace


class FaceTracker:
    """Assigns stable IDs to faces across frames.

    Args:
        max_shift_ratio: Maximum allowed centroid movement between frames,
            as a fraction of the frame diagonal.
        max_missing_frames: How many frames a face may be absent before
            its track is dropped.
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
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    @property
    def active_ids(self) -> list[int]:
        return sorted(self._tracks.keys())

    def reset(self) -> None:
        """Forget all tracks and restart the ID counter."""
        self._tracks.clear()
        self._next_id = 1

    def update(
        self,
        boxes: Sequence[FaceBox],
        frame_width: int,
        frame_height: int,
    ) -> list[TrackedFace]:
        """Feed one frame's detections; returns the faces *visible* in it.

        Faces that were matched this frame are returned (ordered by ID).
        A face that temporarily disappears keeps its track (and therefore
        its ID on return) for up to ``max_missing_frames``, but is not
        reported as visible while absent.
        """
        diagonal = max(1.0, math.hypot(frame_width, frame_height))
        max_distance = self._max_shift_ratio * diagonal

        visible: list[TrackedFace] = []
        unmatched_boxes = list(boxes)
        for track in self._tracks.values():
            if not unmatched_boxes:
                track.miss()
                continue
            best_index, best_distance = self._nearest(
                track.last_box, unmatched_boxes, diagonal
            )
            if best_index is not None and best_distance <= max_distance:
                track.hit(unmatched_boxes.pop(best_index))
                visible.append(
                    TrackedFace(id=track.face_id, bbox=track.last_box)
                )
            else:
                track.miss()

        for box in unmatched_boxes:
            self._tracks[self._next_id] = _Track(
                face_id=self._next_id, last_box=box
            )
            visible.append(TrackedFace(id=self._next_id, bbox=box))
            self._next_id += 1

        for face_id in [fid for fid, t in self._tracks.items() if t.is_expired(self._max_missing_frames)]:
            del self._tracks[face_id]

        return sorted(visible, key=lambda face: face.id)

    @staticmethod
    def _nearest(
        reference: FaceBox,
        candidates: Sequence[FaceBox],
        diagonal: float,
    ) -> tuple[int | None, float]:
        """Index of the candidate closest to the reference centroid."""
        rx, ry = reference.centroid()
        best_index: int | None = None
        best_distance = float("inf")
        for i, candidate in enumerate(candidates):
            cx, cy = candidate.centroid()
            distance = math.hypot(cx - rx, cy - ry)
            if distance < best_distance:
                best_distance = distance
                best_index = i
        return best_index, best_distance


class _Track:
    """Internal state of one tracked face."""

    __slots__ = ("face_id", "last_box", "missing")

    def __init__(self, face_id: int, last_box: FaceBox) -> None:
        self.face_id = face_id
        self.last_box = last_box
        self.missing = 0

    def hit(self, box: FaceBox) -> None:
        self.last_box = box
        self.missing = 0

    def miss(self) -> None:
        self.missing += 1

    def is_expired(self, max_missing: int) -> bool:
        return self.missing > max_missing
