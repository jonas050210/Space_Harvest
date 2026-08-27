"""Reusable UI components of the design system (v1.4).

Small, focused building blocks — no God widgets. All values they show
come from real system data; the components themselves never invent
status or progress.

Status palette (meaning only, never decoration):

    LIVE, READY, PROCESSING, OFFLINE, ERROR, CPU, GPU, MOCK, UNTESTABLE
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

#: Status -> accent color. Colors carry meaning exclusively.
_STATUS_COLORS = {
    "live": "#2bd97c",
    "ready": "#2bd97c",
    "processing": "#00d9ff",
    "offline": "#ff5d5d",
    "error": "#ff5d5d",
    "cpu": "#8fa3b4",
    "gpu": "#2bd97c",
    "mock": "#ffb454",
    "untestable": "#a78bfa",
    # legacy aliases (kept for compatibility)
    "running": "#00d9ff",
    "idle": "#64788a",
    "unknown": "#64788a",
    "success": "#2bd97c",
    "warning": "#ffb454",
}

#: All nine meaningful statuses (documented contract).
MEANINGFUL_STATUSES: tuple[str, ...] = (
    "live", "ready", "processing", "offline", "error",
    "cpu", "gpu", "mock", "untestable",
)


def status_color(status: str) -> str:
    """Theme-aware semantic color for a status ('live', 'mock', ...).

    Colors carry meaning exclusively — see MEANINGFUL_STATUSES. Falls
    back to the dark palette until a theme has been applied.
    """
    try:
        from app.ui import theme

        return theme.semantic_color(status)
    except Exception:  # noqa: BLE001 — color lookup must never crash
        return _STATUS_COLORS.get(status.lower(), "#64788a")


def enable_hover(widget: QWidget) -> None:
    """Enable ``:hover`` stylesheet support on plain widgets (QFrame)."""
    widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)


class PulseDot(QLabel):
    """A status dot that softly pulses while active (GUI thread only)."""

    def __init__(self, color: str = "#2bd97c", parent: Optional[QWidget] = None):
        super().__init__("●", parent)
        self._base_color = color
        self.setStyleSheet(f"color: {color}; font-size: 13px;")
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._timer = QTimer(self)
        self._timer.setInterval(900)
        self._timer.timeout.connect(self._on_tick)
        self._phase = 0

    def set_active(self, active: bool) -> None:
        if active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._effect.setOpacity(1.0)

    def _on_tick(self) -> None:
        self._phase = (self._phase + 1) % 2
        self._effect.setOpacity(1.0 if self._phase == 0 else 0.45)


class SectionHeader(QFrame):
    """Section title row with an optional trailing action/count widget."""

    def __init__(
        self,
        text: str,
        parent: Optional[QWidget] = None,
        action: Optional[QWidget] = None,
        count: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sectionHeader")
        enable_hover(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(8)
        title = QLabel(text.upper())
        title.setObjectName("panel_title")
        layout.addWidget(title)
        if count is not None:
            counter = QLabel(count)
            counter.setObjectName("value_dim")
            layout.addWidget(counter)
        layout.addStretch(1)
        if action is not None:
            layout.addWidget(action)


class MetricCard(QFrame):
    """Compact metric card: label + monospace value (+ optional detail)."""

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        initial: str = "—",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        enable_hover(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        caption = QLabel(title.upper())
        caption.setObjectName("kpi_label")
        self.value_label = QLabel(initial)
        self.value_label.setObjectName("value")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("hint")
        self.detail_label.setVisible(False)
        layout.addWidget(caption)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, text: str, status: str = "") -> None:
        if self.value_label.text() != text:
            self.value_label.setText(text)
        if status:
            self.value_label.setStyleSheet(f"color: {status_color(status)};")
        else:
            self.value_label.setStyleSheet("")

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)
        self.detail_label.setVisible(bool(text))


class StatusBadge(QLabel):
    """Colored status pill (READY / LIVE / OFFLINE / PROCESSING / ...).

    Purely a label — the text (with the ● marker) is read by tests, so
    no child widgets are used. For a pulsing dot, use :class:`PulseDot`
    directly (see the header bar).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.set_status("idle", "—")

    def set_status(self, status: str, text: str = "") -> None:
        label = (text or status).upper()
        color = status_color(status)
        self.setText(f"● {label}")
        self.setStyleSheet(
            f"color: {color};"
            "font-family: 'JetBrains Mono', Consolas, monospace;"
            "font-size: 11px; font-weight: 600; letter-spacing: 1px;"
        )


class EmptyState(QWidget):
    """Professional empty state: glyph + message + detail + action."""

    def __init__(
        self,
        message: str,
        detail: str = "",
        action_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)
        layout.addStretch(1)

        glyph = QLabel("▭")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet("color: #2a3f54; font-size: 26px;")
        layout.addWidget(glyph)

        title = QLabel(message)
        title.setObjectName("value")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        if detail:
            hint = QLabel(detail)
            hint.setObjectName("hint")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            layout.addWidget(hint)

        self.action_button: Optional[QPushButton] = None
        if action_text:
            row = QHBoxLayout()
            row.addStretch(1)
            self.action_button = QPushButton(action_text)
            self.action_button.setObjectName("primary")
            row.addWidget(self.action_button)
            row.addStretch(1)
            layout.addLayout(row)

        layout.addStretch(1)


class NavButton(QPushButton):
    """Left navigation item (checkable, icon + label)."""

    def __init__(
        self,
        key: str,
        label: str,
        icon_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.page_key = key
        self.setText(f"{icon_text}  {label}".strip())
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setProperty("nav", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
