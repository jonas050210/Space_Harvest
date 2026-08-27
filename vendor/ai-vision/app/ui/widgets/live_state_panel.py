"""Compact live vision HUD cards (left column under the camera).

Every value comes from real system data: capture FPS from the FPSMeter,
delegate state from the modules' own reports, all vision counts from the
current VisionResult. Cards show "—" when no data exists — never fake
values.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from app.core.types import VisionResult
from app.ui.components import status_color

#: (key, title, live-accent) — order defines the grid.
_CARDS = (
    ("camera", "CAMERA", True),
    ("fps", "FPS", False),
    ("gpu", "COMPUTE", False),
    ("persons", "PERSONS", False),
    ("faces", "FACES", False),
    ("hands", "HANDS", False),
    ("gesture", "GESTURE", False),
    ("gaze", "GAZE CONF", False),
    ("body", "BODY", False),
    ("objects", "OBJECTS", False),
    ("llm", "AI", True),
    ("image", "IMAGE", True),
)


def _card(title: str) -> tuple[QWidget, QLabel]:
    card = QWidget()
    card.setObjectName("panel")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(2)
    caption = QLabel(title)
    caption.setObjectName("kpi_label")
    value = QLabel("—")
    value.setObjectName("value")
    layout.addWidget(caption)
    layout.addWidget(value)
    return card, value


class LiveStatePanel(QWidget):
    """Grid of live indicator cards (3 columns x 4 rows)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("liveStatePanel")
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)

        self._values: dict[str, QLabel] = {}
        for index, (key, title, _accent) in enumerate(_CARDS):
            card, value = _card(title)
            layout.addWidget(card, index // 3, index % 3)
            self._values[key] = value

        self.set_live(False)
        self.set_delegate({})

    # ------------------------------------------------------------------
    def _set(self, name: str, text: str, color: Optional[str] = None) -> None:
        label = self._values[name]
        if label.text() != text:
            label.setText(text)
        if color:
            label.setStyleSheet(f"color: {color};")
        else:
            label.setStyleSheet("")

    def set_live(self, running: bool) -> None:
        self._set(
            "camera",
            "● LIVE" if running else "○ STANDBY",
            status_color("live" if running else "idle"),
        )

    def set_fps(self, fps: float) -> None:
        self._set("fps", f"{fps:.1f}")

    def set_delegate(self, summary: dict[str, str]) -> None:
        """Real compute state: GPU only when a module reports it."""
        if not summary:
            self._set("gpu", "—")
            return
        if any("gpu" in message for message in summary.values()):
            self._set("gpu", "GPU", status_color("gpu"))
        else:
            self._set("gpu", "CPU", status_color("cpu"))

    def set_result(self, result: Optional[VisionResult], running: bool) -> None:
        if result is None or not running:
            for name in ("persons", "faces", "hands", "gesture", "gaze", "body", "objects"):
                self._set(name, "—")
            return
        self._set("persons", f"{len(result.persons):02d}")
        self._set("faces", f"{len(result.faces):02d}")
        self._set("hands", f"{len(result.hands):02d}")
        gestures = [g.gesture for g in result.gestures]
        self._set("gesture", gestures[0] if gestures else "—")
        gaze = result.gaze
        if gaze is not None and gaze.valid:
            self._set("gaze", f"{int(gaze.confidence * 100)}%")
        else:
            self._set("gaze", "—")
        body = result.body
        if body is not None and body.present:
            arms = body.arm_states
            if arms and all(state != "UNKNOWN" for state in arms.values()):
                self._set("body", f"{arms.get('left', '')}/{arms.get('right', '')}")
            else:
                self._set("body", "TRACKED", status_color("live"))
        else:
            self._set("body", "—")
        self._set("objects", f"{len(result.objects):02d}")

    def set_ai_status(self, text: str, ok: bool = True) -> None:
        self._set("llm", text, status_color("ready" if ok else "error"))

    def set_image_status(self, text: str, ok: bool = True) -> None:
        self._set("image", text, status_color("ready" if ok else "error"))

    def apply_palette(self) -> None:
        """Re-apply theme colors (called on theme toggle)."""
