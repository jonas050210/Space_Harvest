"""Bottom status bar: FPS, frame time, camera state, CPU/RAM."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class StatusPanel(QFrame):
    """Monospace measurement strip along the bottom of the window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(28)

        self.fps_label = self._make_cell(layout, "FPS:", "—")
        self.frame_time_label = self._make_cell(layout, "Frame Time:", "—")
        self.camera_label = self._make_cell(layout, "Camera:", "STANDBY")
        self.resolution_label = self._make_cell(layout, "Resolution:", "—")
        self.cpu_label = self._make_cell(layout, "CPU:", "—")
        self.ram_label = self._make_cell(layout, "RAM:", "—")
        layout.addStretch(1)

    @staticmethod
    def _make_cell(layout: QHBoxLayout, caption: str, initial: str) -> QLabel:
        """Add a caption/value pair to the layout; return the value label."""
        key = QLabel(caption)
        key.setObjectName("kpi_label")
        value = QLabel(initial)
        value.setObjectName("value_dim")
        layout.addWidget(key)
        layout.addWidget(value)
        return value

    def set_fps(self, fps: float, frame_time_ms: float) -> None:
        self.fps_label.setText(f"{fps:.1f}")
        self.frame_time_label.setText(f"{frame_time_ms:.1f} ms")

    def set_camera_state(self, active: bool) -> None:
        self.camera_label.setText("ACTIVE" if active else "STANDBY")

    def set_resolution(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self.resolution_label.setText(f"{width}×{height}")
        else:
            self.resolution_label.setText("—")

    def set_performance(self, cpu: float | None, ram_mb: float | None) -> None:
        self.cpu_label.setText(f"{cpu:.0f}%" if cpu is not None else "—")
        self.ram_label.setText(f"{ram_mb:.0f} MB" if ram_mb is not None else "—")
