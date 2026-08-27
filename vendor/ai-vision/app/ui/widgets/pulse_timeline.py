"""Scene Pulse (Phase 26) — one-strip timeline of recent scene events.

A compact custom-painted widget: the last N minutes of live events
(person entered/left, arm raised, movement, objects, face, gestures)
as colored ticks on a time axis. Real data only — the controller's
bounded event list feeds it; an empty session shows "NO EVENTS" and a
clean axis. Repaints are cheap (O(events), only on data changes).
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

#: Event type -> mark color (consistent with the semantic palette).
_EVENT_COLORS = {
    "PERSON_APPEARED": "#2bd97c",
    "PERSON_LEFT": "#ff5d5d",
    "ARM_RAISED": "#ffb454",
    "ARM_LOWERED": "#ffb454",
    "MOVEMENT_STARTED": "#00d9ff",
    "MOVEMENT_STOPPED": "#00d9ff",
    "FACE_DETECTED": "#8fa3b4",
    "FACE_LOST": "#8fa3b4",
    "OBJECT_APPEARED": "#a78bfa",
    "OBJECT_DISAPPEARED": "#a78bfa",
    "GESTURE_CHANGED": "#ffb454",
    "HAND_MOVED": "#ffb454",
    "GAZE_CHANGED": "#2bd97c",
    "SCENE_CHANGED": "#64788a",
}

#: Bounded number of marks drawn per repaint (visual cap only).
_MAX_MARKS = 300


class PulseTimeline(QWidget):
    """Minimal event timeline (height ~46 px, width-agnostic)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(46)
        self.setMaximumHeight(56)
        self._events: list[tuple[float, str]] = []
        self._window_seconds = 300.0
        self._now = None
        self._clock = None

    # ------------------------------------------------------------------
    def set_clock(self, clock) -> None:
        """Injectable monotonic clock (tests)."""
        self._clock = clock

    def set_window_seconds(self, seconds: float) -> None:
        self._window_seconds = max(60.0, seconds)
        self.update()

    def set_events(self, events: Sequence, now: Optional[float] = None) -> None:
        """Feed (event.timestamp, event.type) pairs (bounded input)."""
        import time as _time

        now_value = now if now is not None else (
            self._clock() if self._clock is not None else _time.monotonic()
        )
        self._events = []
        for event in events:
            try:
                timestamp = float(getattr(event, "timestamp", 0.0))
            except (TypeError, ValueError):
                continue  # malformed events are skipped, never crash
            self._events.append(
                (timestamp, str(getattr(event, "type", "?")))
            )
        self._now = now_value
        self.update()

    def clear(self) -> None:
        self._events = []
        self._now = None
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 6, -8, -6)
        width = max(1.0, float(rect.width()))

        # Axis.
        painter.setPen(QColor("#2a3f54"))
        axis_y = rect.bottom() - 8
        painter.drawLine(rect.left(), axis_y, rect.right(), axis_y)

        if not self._events or self._now is None:
            painter.setPen(QColor("#64788a"))
            painter.setFont(QFont("sans-serif", 8))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter, "NO EVENTS — LIVE SESSION EMPTY"
            )
            painter.end()
            return

        window = self._window_seconds
        visible = [
            (t, kind) for t, kind in self._events
            if self._now - t <= window
        ][-_MAX_MARKS:]

        for timestamp, kind in visible:
            # Newest at the right edge, older to the left.
            age = max(0.0, self._now - timestamp)
            fraction = age / window
            x = rect.right() - int(fraction * width)
            color = QColor(_EVENT_COLORS.get(kind, "#64788a"))
            painter.setPen(color)
            height = 10 if kind in (
                "PERSON_APPEARED", "PERSON_LEFT", "ARM_RAISED",
                "MOVEMENT_STARTED",
            ) else 6
            painter.drawLine(x, axis_y - height, x, axis_y)

        # Window label (right-aligned, muted).
        painter.setPen(QColor("#64788a"))
        painter.setFont(QFont("sans-serif", 8))
        minutes = int(window / 60.0)
        label = f"LAST {minutes} MIN" if minutes >= 1 else f"LAST {int(window)} S"
        painter.drawText(
            rect.adjusted(0, 0, -2, 0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            label,
        )
        painter.end()


class PulsePanel(QWidget):
    """Titled wrapper: caption + timeline (used on VISION and INSIGHTS)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        caption = QLabel("SCENE PULSE")
        caption.setObjectName("panel_title")
        layout.addWidget(caption)
        self.timeline = PulseTimeline(self)
        layout.addWidget(self.timeline)
