"""ANALYZE panel (v1.4): upload, structured results, comparison, feedback.

Layout: a summary strip with three metric cards (MATCH / CONFIDENCE /
QUALITY — real analysis values only), then the structured report
(objects, pose, face, composition, lighting, detail), then a simple
feedback form: WHAT SHOULD CHANGE? -> category -> text -> apply.

The analysis itself runs in worker threads (ImageAnalysisEngine); this
panel only renders structured ImageAnalysisResult data and collects user
feedback. Feedback is stored on the image record and used for prompt
refinement on regeneration — never ignored.
"""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.types import ImageAnalysisResult
from app.ui.components import MetricCard

def _report_colors() -> dict[str, str]:
    """Theme-aware report palette (re-read on every render — cheap)."""
    from app.ui.theme import palette

    tokens = palette()
    return {
        "good": tokens.get("success", "#2bd97c"),
        "bad": tokens.get("danger", "#ff5d5d"),
        "warn": tokens.get("warn", "#ffb454"),
        "muted": tokens.get("muted", "#64788a"),
        "text": tokens.get("text", "#d8e2ea"),
    }


class _Bridge(QObject):
    result = Signal(object)   # ImageAnalysisResult
    error = Signal(str)
    feedback_saved = Signal(str)


class ImageAnalysisPanel(QWidget):
    """Analysis + feedback panel for one selected image."""

    upload_clicked = Signal()
    analyze_clicked = Signal()
    compare_clicked = Signal()
    regenerate_clicked = Signal()
    feedback_submitted = Signal(str, str, str)  # rating, category, text

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._bridge = _Bridge()
        self._bridge.result.connect(self._on_result)
        self._bridge.error.connect(self._on_error)
        self._bridge.feedback_saved.connect(self._on_feedback_saved)
        self._result: Optional[ImageAnalysisResult] = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.status_label = QLabel("ANALYSIS: IDLE")
        self.status_label.setObjectName("hint")
        header.addWidget(self.status_label)
        header.addStretch(1)
        self.upload_button = QPushButton("UPLOAD IMAGE")
        self.upload_button.clicked.connect(self.upload_clicked)
        header.addWidget(self.upload_button)
        self.analyze_button = QPushButton("ANALYZE SELECTED")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze_clicked)
        header.addWidget(self.analyze_button)
        self.compare_button = QPushButton("COMPARE")
        self.compare_button.clicked.connect(self.compare_clicked)
        header.addWidget(self.compare_button)
        layout.addLayout(header)

        # ---------------- summary strip (real values only) ----------------
        strip = QHBoxLayout()
        strip.setSpacing(8)
        self.match_card = MetricCard("MATCH")
        self.confidence_card = MetricCard("CONFIDENCE")
        self.quality_card = MetricCard("QUALITY")
        strip.addWidget(self.match_card)
        strip.addWidget(self.confidence_card)
        strip.addWidget(self.quality_card)
        layout.addLayout(strip)

        self.report = QTextBrowser()
        self.report.setMinimumHeight(200)
        layout.addWidget(self.report, 1)

        # ---------------- feedback ----------------
        feedback_title = QLabel("WHAT SHOULD CHANGE?")
        feedback_title.setObjectName("panel_title")
        layout.addWidget(feedback_title)

        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        category_label = QLabel("Category:")
        category_label.setObjectName("kpi_label")
        category_row.addWidget(category_label)
        self.category_combo = QComboBox()
        for category in ("OBJECT", "POSE", "FACE", "ARM", "HAND",
                         "LIGHTING", "BACKGROUND", "COMPOSITION", "STYLE",
                         "DETAIL", "OTHER"):
            self.category_combo.addItem(category, category.lower())
        category_row.addWidget(self.category_combo, 1)
        layout.addLayout(category_row)

        self.feedback_edit = QLineEdit()
        self.feedback_edit.setPlaceholderText(
            'e.g. "The arm is wrong" or "make it more realistic"'
        )
        layout.addWidget(self.feedback_edit)

        action_row = QHBoxLayout()
        self.correct_button = QPushButton("CORRECT")
        self.correct_button.clicked.connect(
            lambda: self._submit_feedback("correct")
        )
        action_row.addWidget(self.correct_button)
        self.partial_button = QPushButton("PARTIALLY CORRECT")
        self.partial_button.clicked.connect(
            lambda: self._submit_feedback("partial")
        )
        action_row.addWidget(self.partial_button)
        self.wrong_button = QPushButton("WRONG")
        self.wrong_button.setObjectName("danger")
        self.wrong_button.clicked.connect(
            lambda: self._submit_feedback("wrong")
        )
        action_row.addWidget(self.wrong_button)
        layout.addLayout(action_row)

        self.submit_feedback_button = QPushButton("APPLY FEEDBACK")
        self.submit_feedback_button.setObjectName("primary")
        self.submit_feedback_button.clicked.connect(
            lambda: self._submit_feedback("partial")
        )
        self.regenerate_button = QPushButton("REGENERATE WITH FEEDBACK")
        self.regenerate_button.clicked.connect(self.regenerate_clicked)
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.submit_feedback_button, 1)
        apply_row.addWidget(self.regenerate_button, 1)
        layout.addLayout(apply_row)

        self._render_report(None)

    # ------------------------------------------------------------------
    # Result handling
    # ------------------------------------------------------------------
    def set_analyzing(self, active: bool, label: str = "") -> None:
        self.status_label.setText(
            label or ("ANALYZING…" if active else "ANALYSIS: IDLE")
        )
        self.analyze_button.setEnabled(not active)

    def set_result(self, result: Optional[ImageAnalysisResult],
                   source: str = "") -> None:
        self._result = result
        self.status_label.setText(
            f"ANALYSIS: {source or (result.source if result else '')}"
            if result else "ANALYSIS: IDLE"
        )
        self._render_report(result)

    def _on_result(self, result: ImageAnalysisResult) -> None:
        self.set_result(result)

    def _on_error(self, message: str) -> None:
        self.status_label.setText(f"ANALYSIS FAILED — {message[:60]}")
        self.status_label.setObjectName("error_hint")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.analyze_button.setEnabled(True)

    def _on_feedback_saved(self, message: str) -> None:
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    def set_feedback_enabled(self, enabled: bool) -> None:
        """Gate the whole feedback form on having a selected image.

        No action is offered that cannot work right now (workflow rule).
        """
        for widget in (self.correct_button, self.partial_button,
                       self.wrong_button, self.submit_feedback_button,
                       self.feedback_edit, self.category_combo,
                       self.regenerate_button):
            widget.setEnabled(enabled)
        if not enabled:
            self.feedback_edit.setPlaceholderText(
                "Select an image in the gallery first…"
            )
        else:
            self.feedback_edit.setPlaceholderText(
                'e.g. "The arm is wrong" or "make it more realistic"'
            )

    def _submit_feedback(self, rating: str) -> None:
        text = self.feedback_edit.text().strip()
        category = str(self.category_combo.currentData() or "other")
        self.feedback_submitted.emit(rating, category, text)
        self.feedback_edit.clear()
        self._bridge.feedback_saved.emit(
            f"FEEDBACK SAVED ({rating.upper()}) — will be used on regeneration"
        )

    # ------------------------------------------------------------------
    def apply_palette(self) -> None:
        """Re-render with the active theme's colors (theme toggle)."""
        self._render_report(self._result)

    def _render_report(self, result: Optional[ImageAnalysisResult]) -> None:
        colors = _report_colors()
        if result is None:
            self.match_card.set_value("—")
            self.confidence_card.set_value("—")
            self.quality_card.set_value("—")
            self.report.setHtml(
                f"<html><body style='font-size:12px;color:{colors['muted']};'>"
                "No analysis yet. Upload an image or select a gallery "
                "entry and press ANALYZE SELECTED.<br>"
                "Generated images are analyzed automatically when "
                "enabled.</body></html>"
            )
            return

        verdict = result.prompt_match
        verdict_text = (
            verdict.verdict.upper() if verdict.checked else "UNABLE TO DETERMINE"
        )
        confidence = result.confidence
        conf_color = colors['good'] if confidence >= 0.6 else (
            colors['warn'] if confidence >= 0.35 else colors['bad']
        )
        quality = result.quality or {}
        brightness = quality.get("brightness", "—")
        sharpness = quality.get("sharpness", "—")

        # Summary strip (real values only).
        if verdict.checked and verdict.score is not None:
            self.match_card.set_value(
                f"{verdict.score * 100:.0f}%",
                "ready" if verdict.verdict == "good match"
                else "error" if verdict.verdict == "weak match" else "mock",
            )
            self.match_card.set_detail(verdict_text)
        else:
            self.match_card.set_value("—", "untestable")
            self.match_card.set_detail(verdict_text)
        self.confidence_card.set_value(
            f"{confidence * 100:.0f}%",
            "ready" if confidence >= 0.6
            else "mock" if confidence >= 0.35 else "error",
        )
        self.quality_card.set_value(
            f"{brightness} · {sharpness}"
            if brightness != "—" or sharpness != "—" else "—",
        )

        parts: list[str] = [
            "<html><body style='font-size:12px;'>",
            f"<p style='color:{colors['muted']};'>"
            f"{html.escape(str(result.source))} · "
            f"{result.width}×{result.height}</p>",
        ]

        if not result.detectors_available:
            parts.append(
                f"<p style='color:{colors['bad']};'>Detectors unavailable — "
                "content analysis not possible.</p>"
            )

        # Content.
        content = []
        if result.objects:
            content.append("Objects: " + ", ".join(result.objects))
        if result.faces:
            content.append(f"Faces: {result.faces}")
        if result.hands:
            content.append(f"Hands: {result.hands}")
        if result.persons:
            content.append(f"Persons: {result.persons}")
        if result.gestures:
            content.append("Gestures: " + ", ".join(result.gestures))
        if result.pose_present:
            arm_text = (
                f" (arms: {result.arm_states.get('left', '?')} / "
                f"{result.arm_states.get('right', '?')})"
                if result.arm_states else ""
            )
            content.append(f"Body pose: detected{arm_text}")
        if content:
            parts.append("<p style='color:%s;'><b>CONTENT</b><br>" % colors['text']
                         + "<br>".join(html.escape(c) for c in content)
                         + "</p>")

        # Quality.
        if quality:
            parts.append(
                f"<p style='color:{colors['text']};'><b>QUALITY</b><br>"
                f"brightness {brightness} · sharpness {sharpness} · "
                f"{quality.get('resolution', '—')}</p>"
            )

        # Issues.
        if result.issues:
            parts.append(
                f"<p style='color:{colors['bad']};'><b>ISSUES</b><br>"
                + "<br>".join(html.escape(i) for i in result.issues)
                + "</p>"
            )
        else:
            parts.append(
                f"<p style='color:{colors['good']};'>No quality issues detected.</p>"
            )

        # Prompt match.
        match = result.prompt_match
        if match.checked:
            color = colors['good'] if match.verdict == "good match" else (
                colors['bad'] if match.verdict == "weak match" else colors['warn']
            )
            score = f"{match.score * 100:.0f}%" if match.score is not None else "—"
            parts.append(
                f"<p style='color:{color};'><b>PROMPT MATCH</b> — {score} "
                f"({match.verdict})<br>"
                f"matched: {', '.join(match.matched) or 'none'}<br>"
                f"missing: {', '.join(match.missing) or 'none'}<br>"
                f"extra: {', '.join(match.extra) or 'none'}</p>"
            )
        else:
            parts.append(
                f"<p style='color:{colors['muted']};'><b>PROMPT MATCH</b> — unable "
                "to determine (no checkable prompt terms)</p>"
            )

        # Comparison vs vision snapshot.
        # Build HTML ourselves; escape only the untrusted class/gesture names
        # (escaping the whole line would show raw <span> tags).
        comparison = result.comparison
        if comparison:
            lines = ["<b>COMPARISON (vs. vision scene)</b>"]
            if comparison.get("objects_missing"):
                names = ", ".join(
                    html.escape(str(item)) for item in comparison["objects_missing"]
                )
                lines.append(
                    f"<span style='color:{colors['bad']};'>"
                    f"missing objects: {names}</span>"
                )
            if comparison.get("objects_matched"):
                names = ", ".join(
                    html.escape(str(item)) for item in comparison["objects_matched"]
                )
                lines.append(
                    f"<span style='color:{colors['good']};'>"
                    f"present objects: {names}</span>"
                )
            if comparison.get("gestures_missing"):
                names = ", ".join(
                    html.escape(str(item)) for item in comparison["gestures_missing"]
                )
                lines.append(
                    f"<span style='color:{colors['bad']};'>"
                    f"missing gestures: {names}</span>"
                )
            if "pose_present_in_image" in comparison:
                present = "yes" if comparison["pose_present_in_image"] else "no"
                lines.append(f"body pose in image: {present}")
            parts.append(
                "<p style='color:%s;'>%s</p>"
                % (colors["text"], "<br>".join(lines))
            )

        parts.append(
            f"<p style='color:{conf_color};'><b>CONFIDENCE</b> — "
            f"{confidence * 100:.0f}% (heuristic, see documentation)</p>"
        )
        parts.append("</body></html>")
        self.report.setHtml("".join(parts))
