"""INSIGHTS page (Phase 26) — session analytics from real data only.

* ATTENTION metric cards: session length, blinks, blink rate, gaze
  samples, screen coverage, event count — all from the controller's
  RAM-only session state; every card shows "—" until real data exists.
* GAZE HEATMAP preview: the live heatmap rendered into a dark canvas
  (same data as the optional live overlay).
* SCENE PULSE: the session timeline in a wider window (10 minutes).
* SESSION RECAP: deterministic text summary — offline, no LLM.

Nothing here is persisted; the page is fed at 2 Hz while visible.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import MetricCard, SectionHeader
from app.ui.widgets.pulse_timeline import PulsePanel


class HeatmapPreview(QWidget):
    """Dark canvas painting the heatmap overlay (RGBA -> QImage)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(140)
        self._overlay: Optional[np.ndarray] = None

    def set_overlay(self, overlay: Optional[np.ndarray]) -> None:
        """Store the overlay (RGBA, HxWx4) and repaint."""
        self._overlay = overlay
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        overlay = self._overlay
        if overlay is None or overlay.size == 0:
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "NO GAZE DATA YET\nStart the camera — the heatmap "
                "appears here.",
            )
            painter.end()
            return
        # RGBA -> premultiplied-ish paint (alpha via QImage format).
        height, width = overlay.shape[:2]
        image = QImage(
            overlay.data, width, height, width * 4,
            QImage.Format.Format_RGBA8888,
        )
        pixmap = QPixmap.fromImage(image.copy())
        scaled = pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


class InsightsPanel(QWidget):
    """Analytics page content — pure view, fed from the controller."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.reset()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---------------- attention cards ----------------
        layout.addWidget(SectionHeader("ATTENTION"))
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self.cards: dict[str, MetricCard] = {}
        for key, title in (
            ("duration", "SESSION"),
            ("blinks", "BLINKS"),
            ("blink_rate", "BLINKS / MIN"),
            ("samples", "GAZE SAMPLES"),
            ("coverage", "SCREEN COVERAGE"),
            ("events", "EVENTS (10 MIN)"),
        ):
            card = MetricCard(title)
            self.cards[key] = card
            cards_row.addWidget(card)
        layout.addLayout(cards_row)

        # ---------------- heatmap + pulse side by side ----------------
        middle = QHBoxLayout()
        middle.setSpacing(10)

        heat_card = QWidget()
        heat_layout = QVBoxLayout(heat_card)
        heat_layout.setContentsMargins(10, 6, 10, 8)
        heat_layout.setSpacing(4)
        caption = QLabel("GAZE HEATMAP")
        caption.setObjectName("panel_title")
        heat_layout.addWidget(caption)
        self.heatmap = HeatmapPreview(heat_card)
        heat_layout.addWidget(self.heatmap, 1)
        middle.addWidget(heat_card, 1)

        self.pulse = PulsePanel()
        self.pulse.timeline.set_window_seconds(600)
        middle.addWidget(self.pulse, 1)
        layout.addLayout(middle, 1)

        # ---------------- session recap ----------------
        recap_row = QHBoxLayout()
        recap_row.addWidget(SectionHeader("SESSION RECAP"))
        recap_row.addStretch(1)
        self.recap_hint = QLabel("deterministic · offline · RAM-only")
        self.recap_hint.setObjectName("hint")
        recap_row.addWidget(self.recap_hint)
        layout.addLayout(recap_row)
        self.recap = QLabel("")
        self.recap.setObjectName("value_dim")
        self.recap.setWordWrap(True)
        self.recap.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.recap.setMinimumHeight(90)
        layout.addWidget(self.recap)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        for card in self.cards.values():
            card.set_value("—")
        self.heatmap.set_overlay(None)
        self.pulse.timeline.clear()
        self.recap.setText(
            "No session data yet — start the camera and the recap "
            "appears here automatically."
        )

    # ------------------------------------------------------------------
    def update_state(self, state: dict) -> None:
        """Render one analytics snapshot (real values only)."""
        duration = state.get("duration_s", 0.0)
        blinks = state.get("blinks") or {}
        events = state.get("events") or []
        event_summary = state.get("event_summary") or {}
        running = bool(state.get("running"))

        if not running and duration <= 0:
            self.reset()
            return

        from app.session.recap import fmt_duration

        self.cards["duration"].set_value(fmt_duration(duration))
        self.cards["blinks"].set_value(str(blinks.get("count", 0)))
        self.cards["blink_rate"].set_value(
            f"{blinks.get('rate_per_min', 0):.1f}"
        )
        self.cards["samples"].set_value(str(state.get("gaze_samples", 0)))
        coverage = float(state.get("gaze_coverage") or 0.0)
        self.cards["coverage"].set_value(
            f"{coverage * 100:.0f}%" if coverage > 0 else "—"
        )
        recent_events = sum(
            count for name, count in event_summary.items()
            if name != "SCENE_CHANGED"
        )
        self.cards["events"].set_value(str(recent_events))

        overlay = state.get("heatmap_overlay")
        self.heatmap.set_overlay(overlay)
        self.pulse.timeline.set_events(events, now=state.get("now"))

        from app.session.recap import build_session_recap

        self.recap.setText(build_session_recap(
            duration_s=duration,
            blink_stats=blinks,
            gaze_samples=int(state.get("gaze_samples", 0)),
            gaze_coverage=coverage,
            events=events,
            now_running=running,
        ))
