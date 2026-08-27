"""Demo mode overlay (v1.4): translucent step tracker + final summary.

Floats in the top-right corner of the main window while the demo runs.
Shows "AI VISION LAB · DEMO MODE", a progress line, and the numbered
step list; the current step is highlighted and pulses softly. When the
run ends, the tracker switches to a summary card:

    AI VISION LAB
    DEMO COMPLETE
    16/16 STEPS PASSED · 42.1 S

The demo feed itself always carries the "DEMO FEED" watermark, so demo
data can never be mistaken for a real camera. All effects are
QPropertyAnimation-based, GUI thread only.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QVBoxLayout

from app.demo.runner import DemoStep

_STEP_MARK = {
    "pending": "·",
    "running": "●",
    "passed": "✓",
    "failed": "✕",
}
_STEP_COLOR = {
    "pending": "#64788a",
    "running": "#00d9ff",
    "passed": "#2bd97c",
    "failed": "#ff5d5d",
}


class DemoOverlay(QFrame):
    """Semi-transparent demo progress panel with summary mode."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("demoOverlay")
        self.setStyleSheet(
            "#demoOverlay {"
            "  background: rgba(9, 15, 22, 240);"
            "  border: 1px solid #2a3f54;"
            "  border-radius: 12px;"
            "}"
        )
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        self._title = QLabel("AI VISION LAB · DEMO MODE")
        self._title.setObjectName("panel_title")
        layout.addWidget(self._title)

        self._subtitle = QLabel("Automated product run · simulated camera")
        self._subtitle.setObjectName("hint")
        layout.addWidget(self._subtitle)

        self._progress = QLabel("")
        self._progress.setObjectName("value_dim")
        layout.addWidget(self._progress)

        self._labels: dict[str, QLabel] = {}
        self._step_rows = QVBoxLayout()
        self._step_rows.setSpacing(3)
        layout.addLayout(self._step_rows)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setVisible(False)
        layout.addWidget(self._summary)

        self._pulse_effects: dict[str, QGraphicsOpacityEffect] = {}
        self._steps: list[DemoStep] = []

    # ------------------------------------------------------------------
    def set_steps(self, steps: list[DemoStep]) -> None:
        """Build the step list once."""
        self._steps = steps
        while self._step_rows.count():
            item = self._step_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._labels.clear()
        self._pulse_effects.clear()
        for index, step in enumerate(steps, start=1):
            label = QLabel(f"{index:02d} {_STEP_MARK['pending']} {step.label}")
            label.setStyleSheet(
                f"color: {_STEP_COLOR['pending']}; font-size: 12px;"
            )
            effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
            self._step_rows.addWidget(label)
            self._labels[step.key] = label
            self._pulse_effects[step.key] = effect
        self._update_progress()

    # ------------------------------------------------------------------
    def update_step(self, step: Optional[DemoStep]) -> None:
        """Update one step's marker/color; pulse the running one.

        Passing ``None`` (after the run) switches to the final summary.
        """
        if step is None:
            self._show_summary()
            return
        label = self._labels.get(step.key)
        if label is None:
            return
        position = list(self._labels.keys()).index(step.key) + 1
        label.setText(
            f"{position:02d} {_STEP_MARK.get(step.status, '·')} {step.label}"
        )
        label.setStyleSheet(
            f"color: {_STEP_COLOR.get(step.status, '#64788a')};"
            f"font-size: 12px;"
        )

        effect = self._pulse_effects.get(step.key)
        if effect is None:
            return
        if step.status == "running":
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(900)
            animation.setStartValue(1.0)
            animation.setKeyValueAt(0.5, 0.4)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            animation.setLoopCount(-1)
            animation.start()
            effect._demo_pulse = animation  # keep a reference
        else:
            animation = getattr(effect, "_demo_pulse", None)
            if animation is not None:
                animation.stop()
                effect._demo_pulse = None
            effect.setOpacity(1.0)
        self._update_progress()

    def _update_progress(self) -> None:
        finished = sum(
            1 for step in self._steps if step.status in ("passed", "failed")
        )
        self._progress.setText(f"PROGRESS: {finished}/{len(self._steps)}")

    def _show_summary(self) -> None:
        passed = sum(1 for step in self._steps if step.status == "passed")
        total = len(self._steps)
        duration = sum(step.duration_ms or 0.0 for step in self._steps) / 1000.0
        ok = passed == total
        self._title.setText("AI VISION LAB")
        self._subtitle.setText(
            "DEMO COMPLETE" if ok else "DEMO FINISHED WITH FAILURES"
        )
        self._subtitle.setStyleSheet(
            f"color: {'#2bd97c' if ok else '#ff5d5d'};"
            "font-size: 15px; font-weight: 700; letter-spacing: 2px;"
        )
        self._progress.setText(
            f"{passed}/{total} STEPS PASSED · {duration:.1f} s"
        )
        for label in self._labels.values():
            label.setVisible(False)
        failures = [
            step.label for step in self._steps if step.status == "failed"
        ]
        summary = "All systems verified." if ok else (
            "Failed: " + ", ".join(failures)
        )
        self._summary.setText(summary)
        self._summary.setVisible(True)
        self.adjustSize()

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._reposition()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._reposition()
        super().resizeEvent(event)

    def _reposition(self) -> None:
        if self.parentWidget() is not None:
            parent_rect = self.parentWidget().rect()
            self.setGeometry(
                parent_rect.width() - self.width() - 18,
                66,
                self.width(),
                self.height(),
            )
            self.raise_()
