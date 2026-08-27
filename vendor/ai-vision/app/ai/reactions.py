"""AI Reaction Engine: deterministic scene watches.

The user can ask the assistant to *watch* something ("Beobachte meinen
Arm", "Watch my left arm", "Tell me when something moves"). A watch
compares snapshots over time and reports real changes as chat messages —
offline-capable, no LLM required. Cooldowns prevent spam; watches are
RAM-only and removable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.types import SceneSnapshot

#: Watch target ids.
TARGET_ARM_LEFT = "arm_left"
TARGET_ARM_RIGHT = "arm_right"
TARGET_ANY_ARM = "arm_any"
TARGET_MOVEMENT = "movement"
TARGET_FACE = "face"
TARGET_OBJECTS = "objects"

#: Cooldown between two reports of the same watch (seconds). The first
#: (baseline) report is always emitted; subsequent value changes need
#: this spacing to avoid oscillation spam.
_REPORT_COOLDOWN = 0.5


@dataclass
class ReactionWatch:
    """One active watch."""

    target: str
    created_at: float = field(default_factory=time.monotonic)
    last_report_at: float = 0.0
    last_value: Optional[str] = None


class ReactionEngine:
    """Deterministic scene watcher.

    Args:
        report: Callable receiving the watch message (wired to the chat).
    """

    def __init__(self, report: Callable[[str], None],
                 clock=time.monotonic) -> None:
        self._report = report
        self._clock = clock
        self._watches: dict[str, ReactionWatch] = {}

    # ------------------------------------------------------------------
    def watch(self, target: str) -> str:
        """Start a watch; returns the acknowledgment message."""
        labels = {
            TARGET_ARM_LEFT: "left arm",
            TARGET_ARM_RIGHT: "right arm",
            TARGET_ANY_ARM: "arms",
            TARGET_MOVEMENT: "movement",
            TARGET_FACE: "face",
            TARGET_OBJECTS: "objects",
        }
        if target not in labels:
            return "I don't know how to watch that."
        self._watches[target] = ReactionWatch(target=target)
        return (
            f"Watching your {labels[target]}. I will tell you when "
            "something changes."
        )

    def unwatch(self, target: str) -> str:
        if target in self._watches:
            del self._watches[target]
            return "Watch stopped."
        return "No active watch for that target."

    def clear(self) -> None:
        self._watches.clear()

    def active_targets(self) -> list[str]:
        return sorted(self._watches.keys())

    # ------------------------------------------------------------------
    def update(self, snapshot: Optional[SceneSnapshot]) -> None:
        """Feed one snapshot; reports real changes per active watch."""
        if snapshot is None:
            return
        now = self._clock()
        for target, watch in list(self._watches.items()):
            value, message = self._evaluate(target, snapshot)
            if message is None:
                continue
            if value == watch.last_value:
                continue
            if (
                watch.last_value is not None
                and now - watch.last_report_at < _REPORT_COOLDOWN
            ):
                continue
            watch.last_report_at = now
            watch.last_value = value
            self._report(message)

    # ------------------------------------------------------------------
    @staticmethod
    def _evaluate(target: str, snapshot: SceneSnapshot):
        """(value, message) for a watch; message None when nothing to say."""
        if target == TARGET_ARM_LEFT:
            state = snapshot.arm_states.get("left", "UNKNOWN")
            return state, f"Your left arm is now: {state}."
        if target == TARGET_ARM_RIGHT:
            state = snapshot.arm_states.get("right", "UNKNOWN")
            return state, f"Your right arm is now: {state}."
        if target == TARGET_ANY_ARM:
            left = snapshot.arm_states.get("left", "UNKNOWN")
            right = snapshot.arm_states.get("right", "UNKNOWN")
            value = f"{left}|{right}"
            return value, f"Arms changed — left: {left}, right: {right}."
        if target == TARGET_MOVEMENT:
            value = "moving" if snapshot.moving else "still"
            return value, (
                "Movement started." if snapshot.moving else "Movement stopped."
            )
        if target == TARGET_FACE:
            value = str(snapshot.faces)
            if snapshot.faces > 0:
                return value, f"Face detected ({snapshot.faces})."
            return value, "Face lost."
        if target == TARGET_OBJECTS:
            names = sorted(set(snapshot.objects))
            value = "|".join(names)
            if not names:
                return value, "No objects detected anymore."
            return value, f"Objects now: {', '.join(names[:6])}."
        return None, None


#: Natural-language matching for watch requests (EN + DE).
WATCH_PATTERNS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("watch my left arm", "beobachte meinen linken arm",
      "observe my left arm", "linken arm beobachten"), TARGET_ARM_LEFT),
    (("watch my right arm", "beobachte meinen rechten arm",
      "observe my right arm", "rechten arm beobachten"), TARGET_ARM_RIGHT),
    (("watch my arms", "beobachte meine arme", "observe my arms",
      "watch my arm", "beobachte meinen arm"), TARGET_ANY_ARM),
    (("watch movement", "beobachte bewegungen", "tell me when something moves",
      "sage mir wenn sich etwas bewegt", "beobachte die bewegung"),
     TARGET_MOVEMENT),
    (("watch my face", "beobachte mein gesicht", "tell me when a face appears",
      "face detected"), TARGET_FACE),
    (("watch objects", "beobachte objekte", "tell me when objects change",
      "objekte beobachten"), TARGET_OBJECTS),
)


def match_watch_request(query: str) -> Optional[str]:
    """Map a watch request to a target id (None when not a watch request)."""
    normalized = " ".join(query.lower().split())
    for patterns, target in WATCH_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return target
    return None
