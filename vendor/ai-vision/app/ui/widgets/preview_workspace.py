"""Center preview workspace: RESULT / UPLOAD / COMPARE with image slider.

Hosts the generated-image preview, the uploaded-image preview and a
side-by-side comparison with an opacity/position slider. No camera data
is ever stored here — only user-visible previews.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)



def bytes_to_pixmap(png_bytes: bytes) -> Optional[QPixmap]:
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    qimage = QImage(
        rgb.data, width, height, width * 3, QImage.Format.Format_RGB888
    )
    return QPixmap.fromImage(qimage)


class _PreviewLabel(QLabel):
    """Aspect-preserving image label with placeholder text."""

    def __init__(self, placeholder: str) -> None:
        super().__init__(placeholder)
        self._pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(200)
        self.apply_palette()

    def apply_palette(self) -> None:
        """Theme-aware preview surface (dark viewport in both themes —
        it shows images/video, like a camera view)."""
        from app.ui.theme import palette

        tokens = palette()
        self.setStyleSheet(
            f"background: {tokens.get('video', '#04070a')};"
            f"color: {tokens.get('muted', '#64788a')};"
        )

    def set_pixmap_scaled(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pixmap is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
            painter.end()
            return
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


class CompareView(QWidget):
    """Side-by-side + blend slider + DIFF mode comparison of two images."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.left_label = _PreviewLabel("NO IMAGE A")
        self.right_label = _PreviewLabel("NO IMAGE B")
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.left_label, 1)
        row.addWidget(self.right_label, 1)
        layout.addLayout(row, 1)

        # Caption + metadata line for both panes.
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("value_dim")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        slider_row = QHBoxLayout()
        caption = QLabel("BLEND")
        caption.setObjectName("kpi_label")
        slider_row.addWidget(caption)
        self.blend_slider = QSlider(Qt.Orientation.Horizontal)
        self.blend_slider.setRange(0, 100)
        self.blend_slider.setValue(50)
        self.blend_slider.valueChanged.connect(self._on_blend)
        slider_row.addWidget(self.blend_slider, 1)
        self.diff_button = QPushButton("DIFF")
        self.diff_button.setCheckable(True)
        self.diff_button.toggled.connect(self._on_diff_toggled)
        slider_row.addWidget(self.diff_button)
        layout.addLayout(slider_row)

        self._blend = 0.5
        self._diff_mode = False
        self._pixmap_a: Optional[QPixmap] = None
        self._pixmap_b: Optional[QPixmap] = None
        self._meta_a = ""
        self._meta_b = ""

    def set_images(
        self,
        a: Optional[QPixmap],
        b: Optional[QPixmap],
        label_a: str = "",
        label_b: str = "",
        meta_a: str = "",
        meta_b: str = "",
    ) -> None:
        self._pixmap_a = a
        self._pixmap_b = b
        self._meta_a = meta_a
        self._meta_b = meta_b
        self._diff_mode = False
        self.diff_button.setChecked(False)
        self.left_label.set_pixmap_scaled(a)
        self.right_label.set_pixmap_scaled(b)
        if a is None:
            self.left_label.clear()
            self.left_label.setText(label_a or "NO IMAGE A")
        if b is None:
            self.right_label.clear()
            self.right_label.setText(label_b or "NO IMAGE B")
        self._blend = 0.5
        self.blend_slider.setValue(50)
        self._render_meta()

    def _render_meta(self) -> None:
        parts = []
        if self._meta_a:
            parts.append(f"A: {self._meta_a}")
        if self._meta_b:
            parts.append(f"B: {self._meta_b}")
        self.meta_label.setText(" · ".join(parts))

    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_mode = checked
        self._render_diff()

    def _on_blend(self, value: int) -> None:
        self._blend = value / 100.0
        if not self._diff_mode:
            self._render_blend()

    def _render_diff(self) -> None:
        """Pixel difference heatmap (only when both images exist)."""
        if self._diff_mode and self._pixmap_a is not None and self._pixmap_b is not None:
            diff = self._compute_diff(self._pixmap_a, self._pixmap_b)
            if diff is not None:
                self.right_label.set_pixmap_scaled(diff)
                self.right_label.setText("")
                return
        self.right_label.set_pixmap_scaled(self._pixmap_b)
        if self._pixmap_b is None:
            self.right_label.setText("NO IMAGE B")

    @staticmethod
    def _compute_diff(a: QPixmap, b: QPixmap) -> Optional[QPixmap]:
        import cv2
        import numpy as np

        size = min(a.width(), b.width()), min(a.height(), b.height())
        if size[0] < 2 or size[1] < 2:
            return None
        image_a = a.toImage().convertToFormat(QImage.Format.Format_RGB888).scaled(
            size[0], size[1]
        )
        image_b = b.toImage().convertToFormat(QImage.Format.Format_RGB888).scaled(
            size[0], size[1]
        )
        array_a = np.frombuffer(image_a.bits(), dtype=np.uint8).reshape(
            size[1], size[0], 3
        ).copy()
        array_b = np.frombuffer(image_b.bits(), dtype=np.uint8).reshape(
            size[1], size[0], 3
        ).copy()
        diff = cv2.absdiff(array_a, array_b).max(axis=2).astype(np.float32)
        # Heatmap: dark = identical, bright cyan = large change.
        normalized = np.clip(diff / 255.0, 0.0, 1.0)
        heat = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        heat[:, :, 0] = (normalized * 80).astype(np.uint8)
        heat[:, :, 1] = (normalized * 190).astype(np.uint8)
        heat[:, :, 2] = (normalized * 255).astype(np.uint8)
        qimage = QImage(
            heat.data, size[0], size[1], size[0] * 3,
            QImage.Format.Format_RGB888,
        )
        return QPixmap.fromImage(qimage)

    def _render_blend(self) -> None:
        """Overlay blend: image B on top of image A with alpha."""
        if self._pixmap_a is None and self._pixmap_b is None:
            self.right_label.clear()
            self.right_label.setText("NO IMAGES TO COMPARE")
            return
        base = self._pixmap_a if self._pixmap_a is not None else self._pixmap_b
        if self._pixmap_b is None:
            self.right_label.set_pixmap_scaled(base)
            return
        target = base
        if self._pixmap_a is not None and self._pixmap_b is not None:
            result = QPixmap(base.size())
            result.fill(Qt.GlobalColor.transparent)
            painter = QPainter(result)
            painter.drawPixmap(0, 0, self._pixmap_a)
            painter.setOpacity(self._blend)
            painter.drawPixmap(0, 0, self._pixmap_b)
            painter.end()
            target = result
        self.right_label.set_pixmap_scaled(target)


class PreviewWorkspace(QWidget):
    """Center workspace: RESULT / UPLOAD / COMPARE."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("PREVIEW")
        title.setObjectName("panel_title")
        header.addWidget(title)
        header.addStretch(1)
        self.upload_button = QPushButton("UPLOAD IMAGE")
        header.addWidget(self.upload_button)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.result_label = _PreviewLabel("NO GENERATED IMAGE YET")
        self.tabs.addTab(self.result_label, "RESULT")

        self.upload_label = _PreviewLabel("NO IMAGE UPLOADED")
        self.tabs.addTab(self.upload_label, "UPLOAD")

        self.compare_view = CompareView()
        self.tabs.addTab(self.compare_view, "COMPARE")

        layout.addWidget(self.tabs, 1)

        self.info_label = QLabel("")
        self.info_label.setObjectName("hint")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    # ------------------------------------------------------------------
    def show_result(self, png_bytes: bytes, info: str = "") -> None:
        pixmap = bytes_to_pixmap(png_bytes)
        if pixmap is not None:
            self.result_label.set_pixmap_scaled(pixmap)
        else:
            self.result_label.clear()
            self.result_label.setText("INVALID IMAGE DATA")
        self.info_label.setText(info)

    def show_result_info(self, info: str) -> None:
        """Update only the info line (pipeline status without reloading)."""
        self.info_label.setText(info)

    def show_upload(self, png_bytes: bytes, info: str = "") -> None:
        pixmap = bytes_to_pixmap(png_bytes)
        if pixmap is not None:
            self.upload_label.set_pixmap_scaled(pixmap)
        else:
            self.upload_label.clear()
            self.upload_label.setText("INVALID IMAGE DATA")
        self.info_label.setText(info)

    def show_compare(
        self,
        a: Optional[QPixmap],
        b: Optional[QPixmap],
        label_a: str = "",
        label_b: str = "",
        meta_a: str = "",
        meta_b: str = "",
    ) -> None:
        self.compare_view.set_images(
            a, b, label_a=label_a, label_b=label_b,
            meta_a=meta_a, meta_b=meta_b,
        )

    def clear_result(self) -> None:
        self.result_label.clear()
        self.result_label.setText("NO GENERATED IMAGE YET")
