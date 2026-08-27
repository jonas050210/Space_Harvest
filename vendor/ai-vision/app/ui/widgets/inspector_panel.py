"""LIVE INSPECTOR 2.0: categorized details of the tracked person.

All values are real measurements from the current VisionResult plus
pipeline statistics — missing/unreliable values show "—" or UNKNOWN,
never guessed numbers. Sections: HEAD, FACE, BODY, LEFT/RIGHT ARM,
HANDS, OBJECTS, SYSTEM.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.types import VisionResult
from app.ui.components import status_color


def _fmt_angle(value: Optional[float]) -> str:
    return f"{value:+.1f}°" if value is not None else "—"


def _fmt_position(point: Optional[tuple[float, float]]) -> str:
    if point is None:
        return "—"
    return f"{point[0]:.0f} / {point[1]:.0f}"


class InspectorPanel(QWidget):
    """Categorized live-person inspector (VISION page, right column)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("LIVE INSPECTOR")
        title.setObjectName("panel_title")
        header.addWidget(title)
        header.addStretch(1)
        self._state_label = QLabel("NO PERSON")
        self._state_label.setObjectName("hint")
        header.addWidget(self._state_label)
        layout.addLayout(header)

        #: value labels by key (stable keys for tests + UI).
        self._values: dict[str, QLabel] = {}
        layout.addWidget(self._section("HEAD", (
            ("head", "Position (px)"),
            ("head_rot", "Rotation (yaw)"),
            ("head_track", "Tracking"),
        )))
        layout.addWidget(self._section("FACE", (
            ("face", "Detected"),
            ("landmarks", "Landmarks"),
            ("eyes", "Eyes"),
            ("blink", "Blink"),
            ("gaze", "Gaze"),
        )))
        layout.addWidget(self._section("BODY", (
            ("body", "Detected"),
            ("shoulders", "Shoulder tilt"),
            ("center", "Body center"),
            ("movement", "Movement (px/frame)"),
            ("direction", "Direction"),
        )))
        layout.addWidget(self._section("LEFT ARM", (
            ("left_arm", "State · elbow angle"),
            ("left_visibility", "Visibility"),
            ("left_wrist", "Wrist position"),
        )))
        layout.addWidget(self._section("RIGHT ARM", (
            ("right_arm", "State · elbow angle"),
            ("right_visibility", "Visibility"),
            ("right_wrist", "Wrist position"),
        )))
        layout.addWidget(self._section("HANDS", (
            ("hands", "Detected"),
            ("hand_gesture", "Gesture"),
            ("hand_openness", "Openness"),
        )))
        layout.addWidget(self._section("OBJECTS", (
            ("objects", "Count"),
            ("object_names", "Names"),
            ("object_conf", "Best confidence"),
        )))
        layout.addWidget(self._section("SYSTEM", (
            ("sys_fps", "FPS"),
            ("sys_frametime", "Frame time"),
            ("sys_vision_lat", "Vision latency"),
            ("sys_delegate", "Compute"),
            ("sys_generation", "Generation"),
        )))
        layout.addStretch(1)

        self.set_result(None, running=False)

    # ------------------------------------------------------------------
    def _section(self, title: str, rows: tuple[tuple[str, str], ...]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(10, 8, 10, 8)
        section_layout.setSpacing(4)
        caption = QLabel(title)
        caption.setObjectName("panel_title")
        section_layout.addWidget(caption)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for index, (key, label) in enumerate(rows):
            name = QLabel(label)
            name.setObjectName("kpi_label")
            value = QLabel("—")
            value.setObjectName("value")
            grid.addWidget(name, index, 0)
            grid.addWidget(value, index, 1)
            self._values[key] = value
        section_layout.addLayout(grid)
        return frame

    # ------------------------------------------------------------------
    def set_result(
        self,
        result: Optional[VisionResult],
        running: bool,
        fps: float = 0.0,
        frame_time_ms: float = 0.0,
        delegate_summary: Optional[dict[str, str]] = None,
        generation_status: str = "—",
    ) -> None:
        self._clear_all()
        if result is None or not running:
            self._state_label.setText("NO PERSON")
            self._state_label.setStyleSheet("")
            return

        body = result.body
        body_present = body is not None and body.present

        if body_present:
            self._state_label.setText("● PERSON TRACKED")
            self._state_label.setStyleSheet(
                f"color: {status_color('live')};"
            )
            self._set("body", "YES")
        else:
            self._state_label.setText("PERSON — NO BODY DATA")
            self._set("body", "NO")

        # ---------------- HEAD ----------------
        if body_present:
            self._set("head", _fmt_position(body.head_position))
            pose = result.head_pose
            if pose is not None and pose.valid:
                self._set("head_rot", f"{pose.yaw:+.0f}°")
            self._set("head_track", "ACTIVE")
        else:
            self._set("head_track", "NO BODY DATA")

        # ---------------- FACE ----------------
        if result.faces:
            self._set("face", f"YES ({len(result.faces)})")
            self._set("landmarks", str(result.faces[0].landmark_count))
        else:
            self._set("face", "NO")
        eyes = result.eyes
        tracked = [e for e in eyes if e.state == "tracked"]
        self._set("eyes", f"{len(tracked)}/2" if eyes else "—")
        blink = result.blink
        if blink is not None:
            self._set("blink", blink.state)
        gaze = result.gaze
        if gaze is not None and gaze.valid:
            self._set("gaze", f"{gaze.confidence * 100:.0f}%")
        else:
            self._set("gaze", "—")

        # ---------------- BODY ----------------
        if body_present:
            self._set("shoulders", _fmt_angle(body.shoulder_angle_deg))
            self._set("center", _fmt_position(body.centroid))
            self._set("movement", f"{body.movement_speed:.1f}")
            direction = ""
            if body.movement is not None and body.movement_speed > 0.5:
                vx, vy = body.movement
                norm = (vx * vx + vy * vy) ** 0.5 or 1.0
                dx, dy = vx / norm, vy / norm
                if abs(dx) > abs(dy):
                    direction = "RIGHT" if dx > 0 else "LEFT"
                else:
                    direction = "DOWN" if dy > 0 else "UP"
            self._set("direction", direction or "—")

        # ---------------- ARMS ----------------
        for side, prefix, wrist_id in (("left", "left", 15), ("right", "right", 16)):
            if body_present and len(body.landmarks) > wrist_id:
                state = body.arm_states.get(side, "UNKNOWN")
                angle = body.arm_angles.get(side)
                if state == "UNKNOWN" and angle is None:
                    self._set(f"{prefix}_arm", "UNKNOWN")
                elif angle is not None:
                    self._set(f"{prefix}_arm", f"{state} · {angle:.0f}°")
                else:
                    self._set(f"{prefix}_arm", state)
                visibility = float(body.visibility[wrist_id])
                self._set(
                    f"{prefix}_visibility",
                    f"{visibility * 100:.0f}%" if visibility >= 0.05 else "—",
                )
                self._set(
                    f"{prefix}_wrist",
                    _fmt_position(
                        (float(body.landmarks[wrist_id, 0]),
                         float(body.landmarks[wrist_id, 1]))
                    ),
                )
            else:
                self._set(f"{prefix}_arm", "UNKNOWN")

        # ---------------- HANDS ----------------
        self._set("hands", f"{len(result.hands):02d}")
        gestures = [g.gesture for g in result.gestures]
        self._set("hand_gesture", gestures[0] if gestures else "—")
        if result.hands:
            openings = [
                f"{len([s for s in hand.finger_states.values() if s == 'UP'])}/5"
                for hand in result.hands
            ]
            self._set("hand_openness", " · ".join(openings))
        else:
            self._set("hand_openness", "—")

        # ---------------- OBJECTS ----------------
        self._set("objects", f"{len(result.objects):02d}")
        names = [o.class_name for o in result.objects[:4]]
        self._set("object_names", ", ".join(names) if names else "—")
        if result.objects:
            best = max(o.confidence for o in result.objects)
            self._set("object_conf", f"{best * 100:.0f}%")
        else:
            self._set("object_conf", "—")

        # ---------------- SYSTEM ----------------
        if fps > 0:
            self._set("sys_fps", f"{fps:.1f}")
            self._set("sys_frametime", f"{frame_time_ms:.1f} ms")
        if result.processing_ms > 0:
            self._set("sys_vision_lat", f"{result.processing_ms:.0f} ms")
        if delegate_summary:
            if any("gpu" in m for m in delegate_summary.values()):
                self._set("sys_delegate", "GPU", )
            else:
                self._set("sys_delegate", "CPU")
        self._set("sys_generation", generation_status)

    def _set(self, key: str, text: str) -> None:
        label = self._values.get(key)
        if label is not None and label.text() != text:
            label.setText(text)

    def _clear_all(self) -> None:
        for label in self._values.values():
            if label.text() != "—":
                label.setText("—")

    def reset(self) -> None:
        self.set_result(None, running=False)

    def apply_palette(self) -> None:
        """Re-apply theme colors (called on theme toggle)."""
        self._clear_all()
        self._state_label.setText("NO PERSON")
        self._state_label.setStyleSheet("")
