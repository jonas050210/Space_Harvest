"""Vision module toggles and general settings."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from app.config.settings import SettingsService


class ModulesPanel(QFrame):
    """Right-hand panel: enable/disable vision modules + app settings.

    The module rows are generated from the pipeline descriptors, so new
    modules (eye tracking, blink, head pose, ...) appear here automatically.
    """

    module_toggled = Signal(str, bool)   # key, enabled
    setting_changed = Signal(str, object)  # settings key, value

    _SETTING_ROWS = (
        ("dark_theme", "Dark Theme"),
        ("debug_mode", "Debug Mode"),
        ("show_landmark_points", "Landmark Points"),
        ("show_mesh_lines", "Mesh Lines"),
        ("show_eye_overlay", "Eye Overlay"),
        ("gaze_cursor", "Gaze Cursor"),
        ("gaze_trail", "Gaze Trail"),
        ("show_object_overlay", "Object Overlay"),
        ("show_hand_overlay", "Hand Overlay"),
        ("show_body_skeleton", "Body Skeleton"),
        ("show_body_joints", "Body Joints"),
        ("movement_tracking", "Movement Tracking"),
        ("vision_panel", "Vision Panel"),
    )

    _SMOOTHING_LABELS = (
        ("low", "LOW"),
        ("medium", "MEDIUM"),
        ("high", "HIGH"),
    )

    def __init__(self, settings_service: SettingsService, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._module_checkboxes: dict[str, QCheckBox] = {}
        self._setting_checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("VISION MODULES")
        title.setObjectName("panel_title")
        layout.addWidget(title)

        self._modules_layout = QVBoxLayout()
        self._modules_layout.setSpacing(6)
        layout.addLayout(self._modules_layout)

        self._module_hint = QLabel("")
        self._module_hint.setObjectName("hint")
        self._module_hint.setWordWrap(True)
        layout.addWidget(self._module_hint)

        settings_title = QLabel("SETTINGS")
        settings_title.setObjectName("panel_title")
        settings_title.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(settings_title)

        smoothing_row = QHBoxLayout()
        smoothing_row.setSpacing(8)
        smoothing_label = QLabel("Gaze Smoothing:")
        smoothing_label.setObjectName("kpi_label")
        smoothing_row.addWidget(smoothing_label)
        self._smoothing_combo = QComboBox()
        for value, label in self._SMOOTHING_LABELS:
            self._smoothing_combo.addItem(label, value)
        current = str(settings_service.get("gaze_smoothing", "medium"))
        for i in range(self._smoothing_combo.count()):
            if self._smoothing_combo.itemData(i) == current:
                self._smoothing_combo.setCurrentIndex(i)
                break
        self._smoothing_combo.currentIndexChanged.connect(self._on_smoothing_changed)
        smoothing_row.addWidget(self._smoothing_combo, 1)
        layout.addLayout(smoothing_row)

        for key, label_text in self._SETTING_ROWS:
            checkbox = QCheckBox(label_text)
            checkbox.setChecked(bool(settings_service.get(key, False)))
            checkbox.toggled.connect(
                lambda checked, k=key: self.setting_changed.emit(k, checked)
            )
            self._setting_checkboxes[key] = checkbox
            layout.addWidget(checkbox)

        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Settings internals
    # ------------------------------------------------------------------
    def _on_smoothing_changed(self, index: int) -> None:
        value = self._smoothing_combo.itemData(index)
        if value:
            self.setting_changed.emit("gaze_smoothing", value)

    def set_smoothing(self, strength: str) -> None:
        """Update the combo without re-emitting its signal."""
        for i in range(self._smoothing_combo.count()):
            if self._smoothing_combo.itemData(i) == strength:
                self._smoothing_combo.blockSignals(True)
                self._smoothing_combo.setCurrentIndex(i)
                self._smoothing_combo.blockSignals(False)
                return

    # ------------------------------------------------------------------
    # Module rows
    # ------------------------------------------------------------------
    def set_modules(self, descriptors: list[dict[str, str]], enabled_keys: set[str]) -> None:
        """(Re-)build the module toggle rows from pipeline descriptors."""
        while self._modules_layout.count():
            item = self._modules_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._module_checkboxes.clear()
        for descriptor in descriptors:
            key = descriptor["key"]
            checkbox = QCheckBox(f"{descriptor['name']}  [{key}]")
            checkbox.setChecked(key in enabled_keys)
            checkbox.toggled.connect(
                lambda checked, k=key: self.module_toggled.emit(k, checked)
            )
            self._modules_layout.addWidget(checkbox)
            self._module_checkboxes[key] = checkbox

        self._module_hint.setText(self._hint_text(descriptors))

    def set_module_enabled(self, key: str, enabled: bool) -> None:
        """Update a checkbox without re-emitting its signal."""
        checkbox = self._module_checkboxes.get(key)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.blockSignals(False)

    def update_descriptor_status(self, descriptors: list[dict[str, str]]) -> None:
        """Refresh the status hint (e.g. after model loading)."""
        self._module_hint.setText(self._hint_text(descriptors))

    @staticmethod
    def _hint_text(descriptors: list[dict[str, str]]) -> str:
        errors = [
            d for d in descriptors
            if d.get("status") == "error"
        ]
        if not errors:
            return ""
        parts = []
        for d in errors:
            message = (d.get("message") or "").strip()
            if message and "download" in message.lower():
                message = "MODEL NOT AVAILABLE OFFLINE"
            parts.append(
                f"⚠ {d['name']}: {message}" if message else f"⚠ {d['name']}"
            )
        return "\n".join(parts)
