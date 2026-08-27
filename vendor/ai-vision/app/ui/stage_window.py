"""Stage Mode (Phase 25) — clean presentation window for the live feed.

A frameless, always-on-top window showing ONLY the annotated camera
feed plus the minimalist HUD. Built for a second monitor, screen
sharing and product demos: the main window keeps its full studio UI
while the Stage shows the pure vision view.

* Frames are shared by reference (zero copy) from the main window's
  30 Hz poll — the stage never touches the camera or the pipeline.
* Esc hides the stage; F toggles fullscreen (both local to the stage).
* The same HUD values flow into both windows via
  ``update_hud_from_state`` — identical, real numbers.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.config.settings import Settings
from app.ui.hud import HudOverlay
from app.ui.widgets.video_widget import VideoWidget


class StageWindow(QWidget):
    """Frameless live-feed stage (F11 from the main window)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle("AI Vision Lab — Stage")
        self.setMinimumSize(640, 360)
        self.resize(1280, 720)
        self.setStyleSheet("QWidget { background: #04070a; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.video_widget = VideoWidget()
        layout.addWidget(self.video_widget)
        self.hud = HudOverlay(self.video_widget)
        self.hud.set_visible(True)
        self.hud.set_live(False)
        self.video_widget.set_placeholder(
            "STAGE MODE", "Start the camera — the live feed appears here."
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Stage-local keys: Esc hides, F toggles fullscreen."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.key() == Qt.Key.Key_F:
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        """Show the latest annotated frame (kept by reference)."""
        self.video_widget.set_frame(frame)

    def set_placeholder(self, text: str, detail: str = "") -> None:
        self.video_widget.set_placeholder(text, detail)

    def refresh_hud(self, fps: float, result, running: bool,
                    settings: Settings) -> None:
        """Mirror the main window's HUD (identical real values)."""
        from app.ui.hud import update_hud_from_state

        self.hud.set_live(running)
        update_hud_from_state(self.hud, fps, result, running, settings)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """The stage closes for real when the app shuts down."""
        super().closeEvent(event)
