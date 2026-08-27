"""Full-area calibration overlay: 9-point gaze calibration flow.

Flow per point: show the target dot -> settle (user focuses it) -> collect
gaze-feature samples -> advance. After the last point the collected data is
fitted (affine regression) and the result is rated qualitatively
(Excellent / Good / Fair / Poor). The user can cancel at any time; the
profile is only persisted when the user confirms SAVE. No camera images
are stored at any point — only the feature averages per target.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.logging_setup import get_logger
from app.vision.eye.calibration import (
    DEFAULT_TARGETS,
    CalibrationPoint,
    fit_calibration,
)

log = get_logger("ui.calibration_overlay")

#: Timing (milliseconds) — kept short enough for daily use, long enough
#: for stable samples.
_SETTLE_MS = 1100
_SAMPLE_INTERVAL_MS = 60
_SAMPLES_PER_POINT = 12

#: Feature type: (iris_h, iris_v, yaw_deg, pitch_deg) or None.
FeatureProvider = Callable[[], Optional[tuple[float, float, float, float]]]


class CalibrationOverlay(QWidget):
    """Modal-like overlay driving the 9-point calibration sequence."""

    finished = Signal(object)  # CalibrationProfile | None (None = cancelled)

    def __init__(
        self,
        parent: QWidget,
        feature_provider: FeatureProvider,
        screen_size: Optional[tuple[int, int]] = None,
        settle_ms: int = _SETTLE_MS,
        sample_interval_ms: int = _SAMPLE_INTERVAL_MS,
        samples_per_point: int = _SAMPLES_PER_POINT,
    ) -> None:
        super().__init__(parent)
        self._feature_provider = feature_provider
        self._screen_size = screen_size
        self._settle_ms = settle_ms
        self._sample_interval_ms = sample_interval_ms
        self._samples_per_point = samples_per_point

        self._targets = list(DEFAULT_TARGETS)
        self._points: list[CalibrationPoint] = []
        self._point_index = 0
        self._samples_taken = 0
        self._active = False
        self._phase = "run"  # "run" | "done" | "failed"
        self._rating = ""

        self._build_ui()
        self._reset_position()
        self._begin_point()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setObjectName("calibrationOverlay")
        self.setStyleSheet(
            "#calibrationOverlay { background: rgba(6, 10, 14, 235); }"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        self._title = QLabel("GAZE CALIBRATION")
        self._title.setObjectName("h1")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._instruction = QLabel("Look at the dot.")
        self._instruction.setObjectName("value")
        self._instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._instruction)

        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        self._progress_label = QLabel("1 / 9")
        self._progress_label.setObjectName("value")
        bottom.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, len(self._targets))
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        bottom.addWidget(self._progress_bar, 1)

        self._save_button = QPushButton("SAVE CALIBRATION")
        self._save_button.setObjectName("primary")
        self._save_button.setVisible(False)
        bottom.addWidget(self._save_button)

        self._retry_button = QPushButton("RETRY")
        self._retry_button.setVisible(False)
        bottom.addWidget(self._retry_button)

        self._cancel_button = QPushButton("CANCEL")
        self._cancel_button.setObjectName("danger")
        bottom.addWidget(self._cancel_button)

        layout.addLayout(bottom)

        self._save_button.clicked.connect(self._on_save)
        self._retry_button.clicked.connect(self._on_retry)
        self._cancel_button.clicked.connect(self._on_cancel)

    def _reset_position(self) -> None:
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

    # ------------------------------------------------------------------
    # Sequence
    # ------------------------------------------------------------------
    def _begin_point(self) -> None:
        self._phase = "run"
        self._samples_taken = 0
        self._points.append(CalibrationPoint(target=self._targets[self._point_index]))
        self._instruction.setText("Look at the dot.")
        self._save_button.setVisible(False)
        self._retry_button.setVisible(False)
        self._cancel_button.setVisible(True)
        self.update()

        # Settle phase: let the user fixate the target before sampling.
        QTimer.singleShot(self._settle_ms, self._sample)

    def _sample(self) -> None:
        if self._phase != "run":
            return
        features = self._feature_provider()
        if features is not None:
            self._points[-1].samples.append(features)
        self._samples_taken += 1
        if self._samples_taken >= self._samples_per_point:
            self._next_point()
        else:
            QTimer.singleShot(self._sample_interval_ms, self._sample)

    def _next_point(self) -> None:
        self._point_index += 1
        if self._point_index >= len(self._targets):
            self._finish()
            return
        self._progress_bar.setValue(self._point_index)
        self._progress_label.setText(f"{self._point_index + 1} / {len(self._targets)}")
        self._begin_point()

    def _finish(self) -> None:
        import time as _time

        self._phase = "done"
        size = self._screen_size or (0, 0)
        profile = fit_calibration(
            self._points,
            screen_width=size[0],
            screen_height=size[1],
            created_at=_time.time(),
        )
        self._profile = profile
        if profile is None:
            self._phase = "failed"
            self._rating = ""
            self._instruction.setText(
                "Calibration failed — face not visible enough.\n"
                "Keep your face steady and well lit, then retry."
            )
            self._cancel_button.setVisible(False)
            self._retry_button.setVisible(True)
            self._progress_bar.setValue(len(self._targets))
            self._progress_label.setText("FAILED")
        else:
            self._rating = profile.quality.capitalize()
            self._instruction.setText(f"Calibration complete\n{self._rating}")
            self._cancel_button.setVisible(False)
            self._save_button.setVisible(True)
            self._retry_button.setVisible(True)
            self._progress_bar.setValue(len(self._targets))
            self._progress_label.setText("COMPLETE")
        self.update()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        log.info("Calibration saved by user (%s)", self._rating)
        self._active = False
        self.hide()
        self.finished.emit(self._profile)
        self.deleteLater()

    def _on_retry(self) -> None:
        self._points = []
        self._point_index = 0
        self._progress_bar.setValue(0)
        self._progress_label.setText("1 / 9")
        self._begin_point()

    def _on_cancel(self) -> None:
        log.info("Calibration cancelled by user")
        self._active = False
        self.hide()
        self.finished.emit(None)
        self.deleteLater()

    # ------------------------------------------------------------------
    # Painting + keys
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        if self._phase == "run" and self._point_index < len(self._targets):
            tx, ty = self._targets[self._point_index]
            cx = int(tx * self.width())
            cy = int(ty * self.height())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#00d9ff"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - 26, cy - 26, 52, 52)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#00d9ff"))
            painter.drawEllipse(cx - 6, cy - 6, 12, 12)
        painter.end()

    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt API
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._reset_position()
        self.setFocus()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self.update()
        super().resizeEvent(event)
