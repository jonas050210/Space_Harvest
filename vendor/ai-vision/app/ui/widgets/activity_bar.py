"""Bottom activity strip: generation queue status + latest vision event."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.image.queue import GenerationJob, format_job_status


class _Bridge(QObject):
    job_status = Signal(object)


class ActivityBar(QWidget):
    """One-line activity feed under the status panel."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(30)
        self._bridge = _Bridge()
        self._bridge.job_status.connect(self._on_job_status)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)

        self.queue_label = QLabel("QUEUE: idle")
        self.queue_label.setObjectName("value_dim")
        layout.addWidget(self.queue_label)

        self.event_label = QLabel("EVENT: —")
        self.event_label.setObjectName("value_dim")
        layout.addWidget(self.event_label)

        self.ai_label = QLabel("LLM —")
        self.ai_label.setObjectName("value_dim")
        layout.addWidget(self.ai_label)

        self.image_label = QLabel("IMG —")
        self.image_label.setObjectName("value_dim")
        layout.addWidget(self.image_label)

        layout.addStretch(1)

    # ------------------------------------------------------------------
    def on_job_status(self, job: GenerationJob) -> None:
        """Worker-thread entry (bridged to the GUI thread)."""
        self._bridge.job_status.emit(job)

    def _on_job_status(self, job: GenerationJob) -> None:
        self.queue_label.setText(f"QUEUE: {format_job_status(job)}")

    def set_queue_text(self, text: str) -> None:
        self.queue_label.setText(text)

    def set_event(self, text: str) -> None:
        self.event_label.setText(f"EVENT: {text}")

    def set_ai_status(self, text: str) -> None:
        self.ai_label.setText(text)

    def set_image_status(self, text: str) -> None:
        self.image_label.setText(text)
