"""Scene change detection and vision events (v2).

A lightweight event layer on top of the SceneSnapshot. Events are only
created from *real* detected changes and are rate-limited (cooldown per
event type, hysteresis for movement and arm states) so the UI/AI never
gets spammed. Deterministic — no ML involved.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.types import SceneSnapshot

#: Gaze quadrant names (0..1 normalized coordinates).
_QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")

#: Default cooldown between two events of the same type (seconds).
_COOLDOWN_DEFAULT = 1.5

#: Arm state hysteresis: a state must differ from the *last emitted*
#: state to produce an event (NEUTRAL<->OUT transitions are normal noise
#: and are filtered to reduce spam).
_ARM_EVENT_STATES = {"RAISED", "DOWN"}


class EventType(str, enum.Enum):
    OBJECT_APPEARED = "OBJECT_APPEARED"
    OBJECT_DISAPPEARED = "OBJECT_DISAPPEARED"
    PERSON_APPEARED = "PERSON_APPEARED"
    PERSON_LEFT = "PERSON_LEFT"
    GESTURE_CHANGED = "GESTURE_CHANGED"
    GAZE_CHANGED = "GAZE_CHANGED"
    SCENE_CHANGED = "SCENE_CHANGED"
    # Phase 11 additions
    ARM_RAISED = "ARM_RAISED"
    ARM_LOWERED = "ARM_LOWERED"
    MOVEMENT_STARTED = "MOVEMENT_STARTED"
    MOVEMENT_STOPPED = "MOVEMENT_STOPPED"
    FACE_DETECTED = "FACE_DETECTED"
    FACE_LOST = "FACE_LOST"
    HAND_MOVED = "HAND_MOVED"


@dataclass
class VisionEvent:
    """One detected change in the scene."""

    type: EventType
    timestamp: float = field(default_factory=time.monotonic)
    details: dict[str, Any] = field(default_factory=dict)


def gaze_quadrant(snapshot: SceneSnapshot) -> Optional[str]:
    """Quadrant of the gaze point (None without gaze data)."""
    if snapshot.gaze is None:
        return None
    x, y, _confidence = snapshot.gaze
    if x < 0.5:
        return _QUADRANTS[0] if y < 0.5 else _QUADRANTS[2]
    return _QUADRANTS[1] if y < 0.5 else _QUADRANTS[3]


class SceneMonitor:
    """Turns consecutive SceneSnapshots into rate-limited VisionEvents."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._last: Optional[_Signature] = None
        self._cooldowns: dict[EventType, float] = {}
        self._last_emitted_arms: dict[str, str] = {}
        self._movement_active = False
        self._hand_positions: Optional[dict] = None

    def reset(self) -> None:
        self._last = None
        self._cooldowns.clear()
        self._last_emitted_arms.clear()
        self._movement_active = False
        self._hand_positions = None

    # ------------------------------------------------------------------
    def _emit(self, events: list[VisionEvent], event_type: EventType,
              now: float, details: dict[str, Any],
              cooldown: float = _COOLDOWN_DEFAULT) -> None:
        """Append an event unless its type is still on cooldown."""
        last = self._cooldowns.get(event_type, -1.0)
        if now - last < cooldown:
            return
        self._cooldowns[event_type] = now
        events.append(VisionEvent(event_type, now, details))

    # ------------------------------------------------------------------
    def update(self, snapshot: Optional[SceneSnapshot]) -> list[VisionEvent]:
        """Diff the snapshot against the previous one; returns events.

        The first update after a reset establishes the baseline and
        produces no events (there is no "before" yet).
        """
        if snapshot is None:
            return []
        current = _Signature(
            persons=snapshot.persons,
            faces=snapshot.faces,
            objects=frozenset(snapshot.objects),
            hands=snapshot.hands,
            gestures=frozenset(snapshot.gestures),
            gaze=gaze_quadrant(snapshot),
            arm_states=dict(snapshot.arm_states),
            moving=snapshot.moving,
        )
        previous, self._last = self._last, current
        if previous is None:
            return []

        events: list[VisionEvent] = []
        now = self._clock()

        # Objects.
        for name in sorted(current.objects - previous.objects):
            self._emit(events, EventType.OBJECT_APPEARED, now,
                       {"object": name})
        for name in sorted(previous.objects - current.objects):
            self._emit(events, EventType.OBJECT_DISAPPEARED, now,
                       {"object": name})

        # Persons.
        if current.persons > previous.persons:
            self._emit(events, EventType.PERSON_APPEARED, now,
                       {"count": current.persons})
        elif current.persons < previous.persons:
            self._emit(events, EventType.PERSON_LEFT, now,
                       {"count": current.persons})

        # Faces (person may be below the body detector's threshold while
        # the face detector still works).
        if current.faces > previous.faces:
            self._emit(events, EventType.FACE_DETECTED, now,
                       {"count": current.faces})
        elif current.faces < previous.faces:
            self._emit(events, EventType.FACE_LOST, now,
                       {"count": current.faces})

        # Gestures.
        if current.gestures != previous.gestures:
            self._emit(events, EventType.GESTURE_CHANGED, now,
                       {"from": sorted(previous.gestures),
                        "to": sorted(current.gestures)})

        # Gaze.
        if current.gaze != previous.gaze:
            self._emit(events, EventType.GAZE_CHANGED, now,
                       {"from": previous.gaze, "to": current.gaze},
                       cooldown=2.5)

        # Arm state changes (hysteresis: only meaningful transitions).
        for side in ("left", "right"):
            old_state = previous.arm_states.get(side, "UNKNOWN")
            new_state = current.arm_states.get(side, "UNKNOWN")
            if new_state == old_state:
                continue
            last_emitted = self._last_emitted_arms.get(side)
            self._last_emitted_arms[side] = new_state
            if new_state == "RAISED":
                self._emit(events, EventType.ARM_RAISED, now,
                           {"arm": side, "state": new_state})
            elif new_state == "DOWN" and last_emitted == "RAISED":
                self._emit(events, EventType.ARM_LOWERED, now,
                           {"arm": side, "state": new_state})

        # Movement start/stop (hysteresis flag).
        if current.moving and not self._movement_active:
            self._movement_active = True
            self._emit(events, EventType.MOVEMENT_STARTED, now, {},
                       cooldown=2.0)
        elif not current.moving and self._movement_active:
            self._movement_active = False
            self._emit(events, EventType.MOVEMENT_STOPPED, now, {},
                       cooldown=2.0)

        # Hand movement: hand count is too coarse — emit when hands
        # appear/disappear only (position deltas need landmark access).
        if current.hands > previous.hands:
            self._emit(events, EventType.HAND_MOVED, now,
                       {"detail": "hand detected", "count": current.hands},
                       cooldown=3.0)
        elif current.hands < previous.hands:
            self._emit(events, EventType.HAND_MOVED, now,
                       {"detail": "hand lost", "count": current.hands},
                       cooldown=3.0)

        if events:
            events.append(VisionEvent(EventType.SCENE_CHANGED, now, {}))
        return events


class _Signature:
    __slots__ = ("persons", "faces", "objects", "hands", "gestures", "gaze",
                 "arm_states", "moving")

    def __init__(
        self,
        persons: int,
        faces: int,
        objects: frozenset[str],
        hands: int,
        gestures: frozenset[str],
        gaze: Optional[str],
        arm_states: dict[str, str],
        moving: bool,
    ) -> None:
        self.persons = persons
        self.faces = faces
        self.objects = objects
        self.hands = hands
        self.gestures = gestures
        self.gaze = gaze
        self.arm_states = arm_states
        self.moving = moving
