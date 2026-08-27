"""Eye tracking / blink / head pose dashboard with calibration actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.core.types import VisionResult

#: Confidence below which the panel shows a LOW CONFIDENCE hint.
_LOW_CONFIDENCE = 0.35


class GazePanel(QFrame):
    """Right-hand dashboard: gaze, eyes, blinks, head pose, calibration."""

    calibrate_clicked = Signal()
    reset_calibration_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._result: Optional[VisionResult] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("EYE TRACKING")
        title.setObjectName("panel_title")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        rows = (
            ("Gaze X", "gaze_x", "—"),
            ("Gaze Y", "gaze_y", "—"),
            ("Confidence", "gaze_conf", "—"),
            ("Left Iris", "left_iris", "—"),
            ("Right Iris", "right_iris", "—"),
            ("Blink", "blink_state", "—"),
            ("Blink Count", "blink_count", "—"),
            ("Blink Rate", "blink_rate", "—"),
            ("Last Blink", "last_blink", "—"),
        )
        for row_index, (row, key, initial) in enumerate(rows):
            label = QLabel(row)
            label.setObjectName("kpi_label")
            value = QLabel(initial)
            value.setObjectName("value")
            grid.addWidget(label, row_index, 0)
            grid.addWidget(value, row_index, 1, Qt.AlignmentFlag.AlignRight)
            setattr(self, f"_{key}", value)

        layout.addLayout(grid)

        self._gaze_hint = QLabel("WAITING FOR FACE")
        self._gaze_hint.setObjectName("hint")
        self._gaze_hint.setWordWrap(True)
        layout.addWidget(self._gaze_hint)

        # Head pose block.
        pose_title = QLabel("HEAD POSE")
        pose_title.setObjectName("panel_title")
        pose_title.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(pose_title)

        pose_grid = QGridLayout()
        pose_grid.setHorizontalSpacing(12)
        pose_grid.setVerticalSpacing(8)
        pose_rows = (("Yaw", "yaw"), ("Pitch", "pitch"), ("Roll", "roll"))
        for row_index, (row, key) in enumerate(pose_rows):
            label = QLabel(row)
            label.setObjectName("kpi_label")
            value = QLabel("—")
            value.setObjectName("value")
            pose_grid.addWidget(label, row_index, 0)
            pose_grid.addWidget(value, row_index, 1, Qt.AlignmentFlag.AlignRight)
            setattr(self, f"_{key}", value)
        layout.addLayout(pose_grid)

        # Calibration block.
        self._calibration_status = QLabel("Calibration: none (using estimates)")
        self._calibration_status.setObjectName("hint")
        self._calibration_status.setWordWrap(True)
        layout.addWidget(self._calibration_status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.calibrate_button = QPushButton("CALIBRATE GAZE")
        self.calibrate_button.setObjectName("primary")
        self.reset_button = QPushButton("RESET")
        buttons.addWidget(self.calibrate_button, 1)
        buttons.addWidget(self.reset_button, 0)
        layout.addLayout(buttons)

        self.calibrate_button.clicked.connect(self.calibrate_clicked)
        self.reset_button.clicked.connect(self.reset_calibration_clicked)

    # ------------------------------------------------------------------
    def set_result(
        self,
        result: Optional[VisionResult],
        blink_stats: dict[str, object],
        running: bool,
    ) -> None:
        """Update the dashboard from the latest pipeline result."""
        self._result = result
        if result is None or not running:
            for name in (
                "gaze_x", "gaze_y", "gaze_conf", "left_iris", "right_iris",
                "blink_state", "blink_count", "blink_rate", "last_blink",
                "yaw", "pitch", "roll",
            ):
                getattr(self, f"_{name}").setText("—")
            self._gaze_hint.setObjectName("hint")
            self._gaze_hint.setText("WAITING FOR FACE")
            self._gaze_hint.style().unpolish(self._gaze_hint)
            self._gaze_hint.style().polish(self._gaze_hint)
            return

        # Gaze (normalized -> pixels of the current video resolution).
        width, height = self._resolution_of(result)
        gaze = result.gaze
        if gaze is not None and gaze.valid:
            self._gaze_x.setText(f"{int(round(gaze.x * width))}")
            self._gaze_y.setText(f"{int(round(gaze.y * height))}")
            self._gaze_conf.setText(f"{int(round(gaze.confidence * 100))}%")
        else:
            self._gaze_x.setText("—")
            self._gaze_y.setText("—")
            self._gaze_conf.setText("—")

        # Iris positions.
        eyes = {eye.side: eye for eye in result.eyes}
        for side, name in (("left", "left_iris"), ("right", "right_iris")):
            eye = eyes.get(side)
            label = getattr(self, f"_{name}")
            if eye is not None and eye.state == "tracked" and eye.iris_h is not None:
                label.setText(
                    f"{int(round(eye.iris_h * 100))}% / {int(round(eye.iris_v * 100))}%"
                )
            else:
                label.setText("—")

        # Blink info.
        blink = result.blink
        if blink is not None:
            self._blink_state.setText(blink.state)
            self._blink_count.setText(str(blink.count))
            self._blink_rate.setText(f"{blink.rate_per_min:.0f}/min")
            last = blink.last_blink_s
            self._last_blink.setText(f"{last:.1f}s" if last is not None else "—")
        else:
            self._blink_count.setText(str(blink_stats.get("count", 0)))
            rate = blink_stats.get("rate_per_min", 0.0)
            self._blink_rate.setText(f"{float(rate):.0f}/min")
            last = blink_stats.get("last_blink_s")
            self._last_blink.setText(f"{float(last):.1f}s" if last else "—")

        # Head pose.
        pose = result.head_pose
        if pose is not None and pose.valid:
            self._yaw.setText(f"{pose.yaw:+.0f}°")
            self._pitch.setText(f"{pose.pitch:+.0f}°")
            self._roll.setText(f"{pose.roll:+.0f}°")
        else:
            self._yaw.setText("—")
            self._pitch.setText("—")
            self._roll.setText("—")

        # Status hint.
        if result.gaze is None or not result.gaze.valid:
            hint = "WAITING FOR FACE"
        elif result.gaze.is_low_confidence:
            hint = "LOW CONFIDENCE"
            self._gaze_hint.setObjectName("error_hint")
        else:
            hint = (
                "ESTIMATED GAZE — calibrated"
                if result.gaze.calibrated
                else "ESTIMATED GAZE — uncalibrated"
            )
            self._gaze_hint.setObjectName("hint")
        self._gaze_hint.setText(hint)
        self._gaze_hint.style().unpolish(self._gaze_hint)
        self._gaze_hint.style().polish(self._gaze_hint)

    def set_calibration_status(self, status: Optional[dict[str, object]]) -> None:
        """Show the calibration profile summary (or the fallback note)."""
        if status is None:
            self._calibration_status.setText("Calibration: none (using estimates)")
        else:
            quality = str(status["quality"]).capitalize()
            self._calibration_status.setText(
                f"Calibration: {quality} ({status['valid_points']}/{status['total_points']} points)"
            )

    def set_calibrating(self, active: bool) -> None:
        self.calibrate_button.setEnabled(not active)
        self.reset_button.setEnabled(not active)
        self.calibrate_button.setText("CALIBRATING …" if active else "CALIBRATE GAZE")

    def reset(self) -> None:
        self.set_result(None, {}, running=False)

    @staticmethod
    def _resolution_of(result: VisionResult) -> tuple[int, int]:
        if result.frame is not None:
            h, w = result.frame.shape[:2]
            if w > 0 and h > 0:
                return w, h
        return 1280, 720
