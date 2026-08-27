"""VISION CONTROLS: collapsible overlay presets and performance mode.

Keeps the VISION page clean: overlay toggles live behind a collapse
toggle. Presets (MINIMAL/BODY/FACE/OBJECTS/FULL) apply real setting
changes; CUSTOM reflects manual toggling. The mode selector maps to the
runtime performance mode (applied via the controller).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import SettingsService
from app.ui.overlays import (
    OVERLAY_PRESETS,
    OVERLAY_TOGGLES,
    apply_overlay_preset,
    detect_preset,
)

_MODES = (("quality", "QUALITY"), ("balanced", "BALANCED"),
          ("performance", "PERFORMANCE"))


class VisionControlsPanel(QFrame):
    """Collapsible overlay + performance controls (real settings only)."""

    mode_changed = Signal(str)  # vision mode key

    def __init__(
        self,
        settings_service: SettingsService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._settings_service = settings_service
        self._collapsed = False
        self._toggles: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("VISION CONTROLS")
        title.setObjectName("panel_title")
        header.addWidget(title)
        header.addStretch(1)
        self.collapse_button = QPushButton("▾")
        self.collapse_button.setObjectName("collapseToggle")
        self.collapse_button.clicked.connect(self._toggle_collapse)
        header.addWidget(self.collapse_button)
        layout.addLayout(header)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        layout.addWidget(self._body)

        # Overlay preset.
        row = QHBoxLayout()
        row.addWidget(QLabel("Overlay preset:"))
        row.addStretch(1)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("CUSTOM", "custom")
        for key, label, _updates in OVERLAY_PRESETS:
            self.preset_combo.addItem(label, key)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self.preset_combo)
        body_layout.addLayout(row)

        # Individual toggles.
        for key, label in OVERLAY_TOGGLES:
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(settings_service.get(key, False)))
            checkbox.toggled.connect(
                lambda checked, k=key: self._on_toggle(k, checked)
            )
            self._toggles[key] = checkbox
            body_layout.addWidget(checkbox)

        # Performance mode.
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        mode_row.addStretch(1)
        self.mode_combo = QComboBox()
        for key, label in _MODES:
            self.mode_combo.addItem(label, key)
        current_mode = str(settings_service.get("vision_mode", "balanced"))
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == current_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        body_layout.addLayout(mode_row)

        self._sync_preset_combo()

    # ------------------------------------------------------------------
    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self.collapse_button.setText("▸" if self._collapsed else "▾")

    def _on_preset_changed(self, index: int) -> None:
        key = self.preset_combo.itemData(index)
        if not key or key == "custom":
            return
        updates = apply_overlay_preset(self._settings_service.settings, key)
        if updates:
            self._settings_service.update(**updates, overlay_preset=key)
        self._sync_toggles()

    def _on_toggle(self, key: str, checked: bool) -> None:
        self._settings_service.update(**{key: checked})
        self._sync_preset_combo()

    def _on_mode_changed(self, index: int) -> None:
        key = self.mode_combo.itemData(index)
        if key:
            self._settings_service.update(vision_mode=key)
            self.mode_changed.emit(str(key))

    def _sync_toggles(self) -> None:
        settings = self._settings_service.settings
        for key, checkbox in self._toggles.items():
            value = bool(getattr(settings, key))
            if checkbox.isChecked() != value:
                checkbox.blockSignals(True)
                checkbox.setChecked(value)
                checkbox.blockSignals(False)

    def _sync_preset_combo(self) -> None:
        preset = detect_preset(self._settings_service.settings)
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == preset:
                if self.preset_combo.currentIndex() != i:
                    self.preset_combo.blockSignals(True)
                    self.preset_combo.setCurrentIndex(i)
                    self.preset_combo.blockSignals(False)
                return

    def set_mode(self, mode: str) -> None:
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == mode:
                if self.mode_combo.currentIndex() != i:
                    self.mode_combo.blockSignals(True)
                    self.mode_combo.setCurrentIndex(i)
                    self.mode_combo.blockSignals(False)
                return
