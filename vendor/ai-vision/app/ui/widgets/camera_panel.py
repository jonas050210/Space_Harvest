"""Camera control panel: device/resolution selection and start/stop."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.camera.camera_manager import CameraInfo, CameraManager
from app.ui.icons import refresh_icon


class CameraPanel(QFrame):
    """Right-hand panel: camera selection, resolution, fps and start/stop."""

    start_clicked = Signal()
    stop_clicked = Signal()
    refresh_clicked = Signal()
    selection_changed = Signal()  # camera/resolution/fps changed by the user

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._cameras: list[CameraInfo] = []
        self._resolutions: list[tuple[int, int]] = []
        self._block_signals = False
        self._error: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("CAMERA")
        title.setObjectName("panel_title")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Camera:"), 0, 0)
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(150)
        grid.addWidget(self.camera_combo, 0, 1)
        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedWidth(38)
        refresh_icon(self.refresh_button, "Rescan for cameras")
        grid.addWidget(self.refresh_button, 0, 2)

        grid.addWidget(QLabel("Resolution:"), 1, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumWidth(150)
        grid.addWidget(self.resolution_combo, 1, 1, 1, 2)

        grid.addWidget(QLabel("Target FPS:"), 2, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(5, 240)
        self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" fps")
        grid.addWidget(self.fps_spin, 2, 1, 1, 2)

        layout.addLayout(grid)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("hint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start_button = QPushButton("START CAMERA")
        self.start_button.setObjectName("primary")
        self.stop_button = QPushButton("STOP CAMERA")
        self.stop_button.setObjectName("danger")
        buttons.addWidget(self.start_button, 1)
        buttons.addWidget(self.stop_button, 1)
        layout.addLayout(buttons)

        # Wiring
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        self.resolution_combo.currentIndexChanged.connect(self._on_selection_changed)
        self.fps_spin.valueChanged.connect(self._on_selection_changed)
        self.start_button.clicked.connect(self.start_clicked)
        self.stop_button.clicked.connect(self.stop_clicked)
        self.refresh_button.clicked.connect(self.refresh_clicked)

        self._update_hint()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def selected_camera_index(self) -> Optional[int]:
        return self.camera_combo.currentData()

    @property
    def selected_resolution(self) -> str:
        data = self.resolution_combo.currentData()
        return data if data else "1280x720"

    @property
    def selected_fps(self) -> int:
        return self.fps_spin.value()

    def set_cameras(self, cameras: list[CameraInfo]) -> None:
        """Fill the camera combo; empty list shows the 'no camera' hint."""
        self._block_signals = True
        self._cameras = cameras
        self.camera_combo.clear()
        for info in cameras:
            self.camera_combo.addItem(info.name, info.index)
        self._block_signals = False
        self._on_camera_changed(self.camera_combo.currentIndex())
        self._update_hint()

    def select_camera(self, index: int) -> bool:
        """Pre-select a camera by index (returns False if unavailable)."""
        for i in range(self.camera_combo.count()):
            if self.camera_combo.itemData(i) == index:
                self.camera_combo.setCurrentIndex(i)
                return True
        return False

    def select_resolution(self, resolution: str) -> None:
        """Pre-select a resolution label ('1280x720'); keeps closest."""
        try:
            wanted = CameraManager.parse_resolution(resolution)
        except ValueError:
            return
        closest = CameraManager.find_closest(wanted, self._resolutions)
        if closest is None:
            return
        for i in range(self.resolution_combo.count()):
            if self.resolution_combo.itemData(i) == f"{closest[0]}x{closest[1]}":
                self.resolution_combo.setCurrentIndex(i)
                return

    def set_resolutions(self, resolutions: list[tuple[int, int]]) -> None:
        """Fill the resolution combo for the currently selected camera."""
        self._block_signals = True
        self._resolutions = resolutions
        self.resolution_combo.clear()
        for width, height in resolutions:
            label = CameraManager.resolution_label((width, height))
            self.resolution_combo.addItem(label, f"{width}x{height}")
        self._block_signals = False
        self._update_hint()

    def set_fps_target(self, fps: int) -> None:
        self._block_signals = True
        self.fps_spin.setValue(fps)
        self._block_signals = False

    def set_running(self, running: bool) -> None:
        """Enable/disable controls depending on the capture state."""
        busy = running
        self.start_button.setEnabled(not busy and self.selected_camera_index is not None)
        self.stop_button.setEnabled(busy)
        self.camera_combo.setEnabled(not busy)
        self.resolution_combo.setEnabled(not busy)
        self.fps_spin.setEnabled(not busy)
        self._update_hint()

    def set_error(self, message: str) -> None:
        """Show a user-facing error hint."""
        self._error = message
        self._update_hint()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _update_hint(self) -> None:
        hint = self.hint_label
        if self._cameras is None or not self._cameras:
            hint.setObjectName("error_hint")
            hint.setText(
                "No camera detected.\nPlease connect a webcam and press ⟳."
            )
        elif self._error:
            hint.setObjectName("error_hint")
            hint.setText(self._error)
        else:
            hint.setObjectName("hint")
            hint.setText("Camera ready — press START CAMERA to begin analysis.")
        hint.style().unpolish(hint)
        hint.style().polish(hint)

    def _on_camera_changed(self, _index: int) -> None:
        if self._block_signals:
            return
        self._error = None
        self._update_hint()
        self.selection_changed.emit()

    def _on_selection_changed(self, *_args: object) -> None:
        if self._block_signals:
            return
        self.selection_changed.emit()
