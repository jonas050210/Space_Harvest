"""Live vision information panel: persons, faces, hands, gestures,
objects, gaze and head pose in one scrollable dashboard.

The content is generated exclusively from the current VisionResult — no
hardcoded objects, no fake data.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.types import VisionResult
from app.ui.annotator import class_color

#: Maximum number of object rows shown (the rest is summarised).
_MAX_OBJECT_ROWS = 12


class VisionPanel(QFrame):
    """Scrollable 'VISION ANALYSIS' dashboard."""

    #: (class_name, confidence, object_id) of a selected object row.
    object_selected = Signal(str, float, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(8)

        title = QLabel("VISION ANALYSIS")
        title.setObjectName("panel_title")
        outer.addWidget(title)

        # Scrollable content area.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(300)
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 0, 6, 0)
        self._layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.set_result(None, running=False)

    # ------------------------------------------------------------------
    def set_result(self, result: Optional[VisionResult], running: bool) -> None:
        """Rebuild the dashboard from the latest pipeline result."""
        self._clear()
        if result is None or not running:
            self._add_hint("WAITING FOR CAMERA")
            return

        if not result.persons and not result.faces and not result.hands and not result.objects:
            self._add_hint("NO VISION DATA — show your face, hands or objects")
            return

        # PERSONS / FACES summary row.
        person_text = self._person_summary(result)
        self._add_row(
            "PERSONS", str(len(result.persons)), detail=person_text
        )
        self._add_row("FACES", str(len(result.faces)))

        # HANDS section.
        self._add_section("HANDS")
        if result.hands:
            gestures = {g.hand_id: g for g in result.gestures}
            for hand in result.hands:
                name = hand.handedness.upper() if hand.handedness else "HAND"
                gesture = gestures.get(hand.id)
                if gesture is not None:
                    detail = (
                        f"{name} #{hand.id} — {gesture.gesture} "
                        f"{gesture.confidence * 100:.0f}%"
                    )
                else:
                    detail = f"{name} #{hand.id} — tracking"
                self._add_detail(detail)
        else:
            self._add_hint("NO HANDS DETECTED")

        # GESTURES section.
        if result.gestures:
            self._add_section("GESTURES")
            for gesture in result.gestures:
                self._add_detail(
                    f"{gesture.gesture}  {gesture.confidence * 100:.0f}%"
                )

        # OBJECTS section.
        self._add_section("OBJECTS")
        if result.objects:
            objects = sorted(
                result.objects, key=lambda obj: obj.confidence, reverse=True
            )
            for obj in objects[:_MAX_OBJECT_ROWS]:
                self._add_object_row(obj.class_name, obj.confidence, obj.id)
            if len(objects) > _MAX_OBJECT_ROWS:
                self._add_hint(f"+ {len(objects) - _MAX_OBJECT_ROWS} more …")
        else:
            self._add_hint("NO OBJECTS DETECTED")

        # GAZE summary.
        gaze = result.gaze
        if gaze is not None and gaze.valid:
            width, height = self._resolution_of(result)
            self._add_row(
                "GAZE",
                f"{int(round(gaze.x * width))} / {int(round(gaze.y * height))}",
                detail=f"{gaze.confidence * 100:.0f}%",
            )

        # HEAD summary.
        pose = result.head_pose
        if pose is not None and pose.valid:
            self._add_row(
                "HEAD",
                f"Yaw {pose.yaw:+.0f}° · Pitch {pose.pitch:+.0f}° · Roll {pose.roll:+.0f}°",
            )

        self._layout.addStretch(1)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_nested(item.layout())

    @staticmethod
    def _clear_nested(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_section(self, name: str) -> None:
        label = QLabel(name)
        label.setObjectName("panel_title")
        self._layout.addWidget(label)

    def _add_row(self, caption: str, value: str, detail: str = "") -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        key = QLabel(caption)
        key.setObjectName("kpi_label")
        val = QLabel(value)
        val.setObjectName("value")
        row.addWidget(key)
        row.addWidget(val)
        row.addStretch(1)
        if detail:
            det = QLabel(detail)
            det.setObjectName("hint")
            row.addWidget(det)
        self._layout.addLayout(row)

    def _add_detail(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("value_dim")
        self._layout.addWidget(label)

    def _add_hint(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("hint")
        self._layout.addWidget(label)

    def _add_object_row(self, class_name: str, confidence: float, object_id: int) -> None:
        """Object row with a select button (real selection from detections)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        r, g, b = class_color(class_name)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: rgb({r}, {g}, {b}); font-size: 12px;")
        name = QLabel(class_name.capitalize())
        name.setObjectName("value_dim")
        conf = QLabel(f"{confidence * 100:.0f}%")
        conf.setObjectName("value")
        select = QPushButton("SELECT")
        select.setFixedWidth(64)
        select.setStyleSheet("QPushButton { padding: 2px 4px; font-size: 10px; }")
        select.clicked.connect(
            lambda _checked=False, n=class_name, c=confidence,
            oid=object_id: self.object_selected.emit(n, c, oid)
        )
        row.addWidget(dot)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(conf)
        row.addWidget(select)
        self._layout.addLayout(row)

    # ------------------------------------------------------------------
    @staticmethod
    def _person_summary(result: VisionResult) -> str:
        links = result.person_face_links
        if not links:
            return ""
        return " · ".join(
            f"#{person_id}→Face #{face_id}" for person_id, face_id in sorted(links.items())
        )

    @staticmethod
    def _resolution_of(result: VisionResult) -> tuple[int, int]:
        if result.frame is not None:
            h, w = result.frame.shape[:2]
            if w > 0 and h > 0:
                return w, h
        return 1280, 720
