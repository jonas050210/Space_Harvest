"""Face analysis dashboard: face count, landmark count, tracking state."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from app.core.types import VisionResult


class AnalysisPanel(QFrame):
    """Live face statistics of the current frame."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("FACE ANALYSIS")
        title.setObjectName("panel_title")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(self._kpi("Faces:"), 0, 0)
        self.faces_label = self._value("0")
        grid.addWidget(self.faces_label, 0, 1, Qt.AlignmentFlag.AlignRight)

        grid.addWidget(self._kpi("Landmarks:"), 1, 0)
        self.landmarks_label = self._value("0")
        grid.addWidget(self.landmarks_label, 1, 1, Qt.AlignmentFlag.AlignRight)

        grid.addWidget(self._kpi("Tracking:"), 2, 0)
        self.tracking_label = self._value("—")
        grid.addWidget(self.tracking_label, 2, 1, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(grid)

    @staticmethod
    def _kpi(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("kpi_label")
        return label

    @staticmethod
    def _value(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("value")
        return label

    def set_result(
        self,
        result: Optional[VisionResult],
        tracking_active: bool,
    ) -> None:
        """Update statistics from a pipeline result (None = no analysis)."""
        if result is None:
            self.faces_label.setText("—")
            self.landmarks_label.setText("—")
            self.tracking_label.setText("—")
            return
        self.faces_label.setText(str(len(result.faces)))
        landmark_count = (
            result.faces[0].landmark_count if result.faces else 0
        )
        self.landmarks_label.setText(str(landmark_count))
        self.tracking_label.setText("ACTIVE" if tracking_active else "—")
