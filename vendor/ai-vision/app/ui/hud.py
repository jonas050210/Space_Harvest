"""Live HUD (v1.4): minimalist glass status strip over the camera feed.

Shows only essential, real values — LIVE state, FPS, PERSONS, OBJECTS,
TRACKING. Optional extras (FACE / HANDS / MOVEMENT) can be enabled.
Values come exclusively from the pipeline result and the FPS meter;
when no data exists the cells show "—". Never a fake number.

Updated at a low frequency (2 Hz) from the main window's frame poll;
drawing is plain Qt — zero cost for the vision worker.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core.types import VisionResult
from app.ui.components import PulseDot, status_color

#: (key, caption, default visible)
_DEFAULT_CELLS: tuple[tuple[str, str], ...] = (
    ("fps", "FPS"),
    ("persons", "PERSONS"),
    ("objects", "OBJECTS"),
    ("tracking", "TRACKING"),
)

#: Optional extras, hidden unless a setting enables them.
_EXTRA_CELLS: tuple[tuple[str, str], ...] = (
    ("faces", "FACE"),
    ("hands", "HANDS"),
    ("movement", "MOVEMENT"),
)


class HudOverlay(QFrame):
    """Glass HUD bar overlaid on the video widget (top-left corner)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("hud")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(14)

        self.live_dot = PulseDot(status_color("live"), self)
        self.live_dot.set_active(False)
        self.live_label = QLabel("STANDBY")
        self.live_label.setObjectName("hudCell")
        self.live_label.setStyleSheet(f"color: {status_color('idle')};")
        layout.addWidget(self.live_dot)
        layout.addWidget(self.live_label)
        layout.addSpacing(4)

        self._cells: dict[str, QLabel] = {}
        for key, caption in _DEFAULT_CELLS:
            cell = self._add_cell(layout, caption)
            self._cells[key] = cell
        for key, caption in _EXTRA_CELLS:
            cell = self._add_cell(layout, caption)
            cell.parentWidget().setVisible(False)
            self._cells[key] = cell

        self.hide()

    @staticmethod
    def _add_cell(layout: QHBoxLayout, caption: str) -> QLabel:
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(0)
        key = QLabel(caption)
        key.setObjectName("hudKey")
        value = QLabel("—")
        value.setObjectName("hudCell")
        wrap_layout.addWidget(key)
        wrap_layout.addWidget(value)
        layout.addWidget(wrap)
        return value

    # ------------------------------------------------------------------
    def set_visible(self, visible: bool) -> None:
        self.setVisible(visible)
        if visible and self.parentWidget() is not None:
            self._reposition()
            self.raise_()

    def set_extras(self, show_face: bool, show_hands: bool,
                   show_movement: bool) -> None:
        """Toggle the optional FACE / HANDS / MOVEMENT cells."""
        for key, visible in (("faces", show_face), ("hands", show_hands),
                             ("movement", show_movement)):
            label = self._cells.get(key)
            if label is not None:
                label.parentWidget().setVisible(visible)

    # ------------------------------------------------------------------
    def set_live(self, running: bool) -> None:
        self._live = running
        self._apply_live_style()

    def _apply_live_style(self) -> None:
        running = getattr(self, "_live", False)
        if running:
            self.live_dot.setStyleSheet(
                f"color: {status_color('live')}; font-size: 12px;"
            )
            self.live_dot.set_active(True)
            self.live_label.setText("LIVE")
            self.live_label.setStyleSheet(f"color: {status_color('live')};")
        else:
            self.live_dot.set_active(False)
            self.live_dot.setStyleSheet(
                f"color: {status_color('idle')}; font-size: 12px;"
            )
            self.live_label.setText("STANDBY")
            self.live_label.setStyleSheet(f"color: {status_color('idle')};")

    def apply_palette(self) -> None:
        """Re-apply theme colors (theme toggle)."""
        self._apply_live_style()

    def update_values(
        self,
        fps: Optional[float] = None,
        result: Optional[VisionResult] = None,
        tracking: Optional[bool] = None,
        movement: Optional[bool] = None,
    ) -> None:
        """Refresh the value cells — pass only real data."""
        # No data (None) or a zero reading both mean "—" — the HUD
        # never keeps a stale value once the camera stops.
        if fps is None or fps <= 0:
            self._set("fps", "—")
        else:
            self._set("fps", f"{fps:.1f}")
        if result is not None:
            self._set("persons", f"{len(result.persons):02d}")
            self._set("objects", f"{len(result.objects):02d}")
            self._set("faces", f"{len(result.faces):02d}")
            self._set("hands", f"{len(result.hands):02d}")
        if tracking is not None:
            self._set("tracking", "ACTIVE" if tracking else "—")
        if movement is not None:
            self._set("movement", "MOVING" if movement else "STATIC")

    def _set(self, key: str, text: str) -> None:
        label = self._cells.get(key)
        if label is not None and label.text() != text:
            label.setText(text)

    def reset(self) -> None:
        for label in self._cells.values():
            if label.text() != "—":
                label.setText("—")

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._reposition()
        super().showEvent(event)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        self.move(8, 8)
        self.raise_()


def update_hud_from_state(
    hud: "HudOverlay",
    fps: float,
    result,
    running: bool,
    settings,
) -> None:
    """Feed one HUD instance with real state (shared by the main window
    and the Stage window — identical values, no duplication drift).

    Values come exclusively from the pipeline result, the FPS meter and
    the module settings; missing data shows "—".
    """
    tracking = bool(result is not None and result.persons)
    movement = bool(
        result is not None and result.body is not None
        and result.body.movement_speed > 0.5
    )
    hud.set_extras(
        bool(settings.face_detection),
        bool(settings.hand_tracking),
        bool(settings.movement_tracking),
    )
    hud.update_values(
        fps=fps if running else None,
        result=result if running else None,
        tracking=tracking if running else False,
        movement=movement if running else None,
    )
