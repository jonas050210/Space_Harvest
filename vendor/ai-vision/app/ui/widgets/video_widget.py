"""Live camera view with aspect-preserving scaling and placeholder states."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

#: QImage wraps the BGR buffer directly (Qt >= 5.14 supports BGR888).
_BGR888 = QImage.Format.Format_BGR888


class VideoWidget(QWidget):
    """Displays the latest annotated frame or a placeholder message."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self._frame_ref: Optional[np.ndarray] = None
        self._image: Optional[QImage] = None
        self._pixmap: Optional[QPixmap] = None
        self._placeholder = "WAITING FOR CAMERA"
        self._placeholder_detail = ""
        self._muted_color = QColor("#64788a")
        self.apply_palette()

    # ------------------------------------------------------------------
    def apply_palette(self) -> None:
        """Pick up the active theme's colors (video viewport stays dark
        in both themes — it is a camera view)."""
        from app.ui.theme import palette

        self._muted_color = QColor(palette().get("muted", "#64788a"))

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def set_frame(self, frame_bgr: Optional[np.ndarray]) -> None:
        """Show a BGR frame (kept by reference — zero-copy display)."""
        if frame_bgr is None:
            self._frame_ref = None
            self._image = None
            self._pixmap = None
            self.update()
            return
        self._frame_ref = np.ascontiguousarray(frame_bgr, dtype=np.uint8)
        height, width = self._frame_ref.shape[:2]
        self._image = QImage(
            self._frame_ref.data,
            width,
            height,
            width * 3,
            _BGR888,
        )
        self._pixmap = None
        self.update()

    def set_placeholder(self, text: str, detail: str = "") -> None:
        """Show a message instead of video (e.g. 'No camera detected')."""
        self.set_frame(None)
        self._placeholder = text
        self._placeholder_detail = detail
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        image = self._image
        if image is None or image.isNull():
            self._paint_placeholder(painter)
            painter.end()
            return

        if self._pixmap is None:
            self._pixmap = QPixmap.fromImage(image)
        pixmap = self._pixmap

        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def _paint_placeholder(self, painter: QPainter) -> None:
        painter.setPen(self._muted_color)
        font = painter.font()
        font.setPointSize(11)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        painter.setFont(font)
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder
        )
        if self._placeholder_detail:
            font.setPointSize(9)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 0.0)
            painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(0, 34, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._placeholder_detail,
        )
