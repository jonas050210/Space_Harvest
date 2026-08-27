"""Top bar (v1.4): product identity, provider status cluster, LIVE state.

Left: AI VISION LAB + version pill. Right: delegate badge (CPU/GPU),
LLM and IMAGE provider badges, the Ctrl+K hint, and the LIVE indicator
(with a subtle pulse). Every badge reflects real provider state — the
header never invents a status.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel

from app.ui.components import status_color


class HeaderBar(QFrame):
    """Header strip with the product name and status cluster."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        self.setFixedHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        title = QLabel("AI VISION LAB")
        title.setObjectName("h1")
        layout.addWidget(title)

        from app import __version__

        version = QLabel(f"v{__version__}")
        version.setObjectName("value_dim")
        version.setStyleSheet(
            "letter-spacing: 1px; padding: 2px 8px;"
            "border: 1px solid #2a3f54; border-radius: 9px;"
        )
        layout.addWidget(version)

        layout.addStretch(1)

        # ------- provider/delegate cluster (real status only) -------
        self.delegate_badge = QLabel("COMPUTE —")
        self.delegate_badge.setObjectName("value_dim")
        layout.addWidget(self.delegate_badge)

        self.llm_badge = QLabel("LLM —")
        self.llm_badge.setObjectName("value_dim")
        layout.addWidget(self.llm_badge)

        self.image_badge = QLabel("IMAGE —")
        self.image_badge.setObjectName("value_dim")
        layout.addWidget(self.image_badge)

        shortcut_hint = QLabel("CTRL+K")
        shortcut_hint.setObjectName("hint")
        layout.addWidget(shortcut_hint)

        # ------- LIVE indicator -------
        self._dot = QLabel("●")
        self._dot.setObjectName("live")
        self._dot.setStyleSheet("font-size: 15px;")
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._status = QLabel("STANDBY")
        self._status.setObjectName("live_off")
        layout.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)

        # Subtle pulse for the LIVE dot — GUI thread only, never touches
        # the vision worker. Stopped while in standby.
        self._pulse_effect = QGraphicsOpacityEffect(self._dot)
        self._dot.setGraphicsEffect(self._pulse_effect)
        self._pulse = QPropertyAnimation(self._pulse_effect, b"opacity", self)
        self._pulse.setDuration(1400)
        self._pulse.setStartValue(1.0)
        self._pulse.setKeyValueAt(0.5, 0.35)
        self._pulse.setEndValue(1.0)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)

    # ------------------------------------------------------------------
    @staticmethod
    def _style_badge(badge: QLabel, text: str, color: str) -> None:
        badge.setText(text)
        badge.setStyleSheet(
            f"color: {color}; letter-spacing: 1px;"
        )

    def set_live(self, live: bool) -> None:
        """Switch the indicator between LIVE and STANDBY."""
        if live:
            self._dot.setObjectName("live")
            self._dot.setText("●")
            self._status.setObjectName("live")
            self._status.setText("LIVE")
            if self._pulse.state() != QPropertyAnimation.State.Running:
                self._pulse.start()
        else:
            self._dot.setObjectName("live_off")
            self._dot.setText("○")
            self._status.setObjectName("live_off")
            self._status.setText("STANDBY")
            self._pulse.stop()
            self._pulse_effect.setOpacity(1.0)
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def set_delegate(self, summary: dict[str, str] | None) -> None:
        """Show the real compute state (GPU only when a module reports it)."""
        if not summary:
            self._style_badge(self.delegate_badge, "COMPUTE —",
                              status_color("idle"))
            return
        gpu = any("gpu" in m for m in summary.values())
        self._style_badge(
            self.delegate_badge,
            "GPU" if gpu else "CPU",
            status_color("gpu" if gpu else "cpu"),
        )

    def set_llm_status(self, status: str) -> None:
        """LLM provider state (online / mock / offline / configured)."""
        text = status.upper()
        if status == "online":
            color = status_color("ready")
        elif status == "mock":
            color = status_color("mock")
            text = "LLM MOCK"
        elif status == "offline":
            color = status_color("offline")
            text = "LLM OFFLINE"
        else:
            color = status_color("idle")
            text = f"LLM {text}"
        self._style_badge(self.llm_badge, text, color)

    def set_image_status(self, status: str) -> None:
        """Image provider state (online / mock / unavailable / ready)."""
        if status == "mock":
            color = status_color("mock")
            text = "IMG MOCK"
        elif status in ("unavailable", "offline"):
            color = status_color("offline")
            text = "IMG OFFLINE"
        elif status == "online":
            color = status_color("ready")
            text = "IMG READY"
        else:
            color = status_color("idle")
            text = f"IMG {status.upper()}"
        self._style_badge(self.image_badge, text, color)
