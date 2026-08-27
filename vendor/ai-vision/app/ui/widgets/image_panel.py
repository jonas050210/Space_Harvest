"""GENERATE tab: prompt, presets, capabilities-driven parameters,
generation queue, cancel, img2img variation and face reference gating.

* All generation runs in a queue worker thread (never blocks vision/GUI).
* Only options the selected provider actually supports are shown —
  unsupported parameters are hidden, no fake sliders.
* The EXTERNAL API provider is clearly marked; prompts are only sent on
  an explicit GENERATE press.
* [GENERATE SCENE] builds a controlled prompt from the current
  SceneSnapshot.
* Face reference ("USE MY FACE") is only enabled when a provider declares
  ``supports_face_reference`` — currently none does, and the UI says so
  honestly instead of faking the feature.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.types import SceneSnapshot
from app.image.engine import ImageGenerationEngine
from app.image.presets import PRESETS, apply_preset
from app.image.prompt_builder import build_scene_prompt
from app.image.queue import (
    COMPLETED,
    FAILED,
    GENERATING,
    GenerationJob,
    format_job_status,
)
from app.ui.errors import format_provider_error
from app.ui.icons import refresh_icon
from app.utils.logging_setup import get_logger

log = get_logger("ui.image_panel")

#: Provider options: (settings key, label)
_PROVIDERS = (
    ("mock", "Mock (dev fallback)"),
    ("sdwebui", "Stable Diffusion WebUI (local)"),
    ("comfyui", "ComfyUI (local)"),
    ("local", "Local endpoint (OpenAI-compatible)"),
    ("external", "EXTERNAL API — prompt leaves this machine"),
)

_PROVIDER_NAMES = {
    key: label.split(" — ")[0] for key, label in _PROVIDERS
}


class _Bridge(QObject):
    models = Signal(list)
    status = Signal(object)  # provider status dict


class ImagePanel(QWidget):
    """Image generation UI with queue and face-reference gating."""

    face_upload_clicked = Signal()
    face_remove_clicked = Signal()
    vary_clicked = Signal()   # img2img from the selected gallery record

    def __init__(
        self,
        engine: ImageGenerationEngine,
        snapshot_provider: Callable[[], Optional[SceneSnapshot]],
        settings_service,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._snapshot_provider = snapshot_provider
        self._settings_service = settings_service
        self._bridge = _Bridge()
        self._bridge.models.connect(self._on_models)
        self._bridge.status.connect(self._on_status)

        self._build_ui()
        self._apply_provider_ui()
        self.refresh_status()
        self._refresh_queue_list()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.status_label = QLabel("IMAGE GENERATION: —")
        self.status_label.setObjectName("hint")
        header.addWidget(self.status_label)
        header.addStretch(1)
        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedWidth(36)
        refresh_icon(self.refresh_button, "Refresh provider status and models")
        self.refresh_button.clicked.connect(self._on_refresh_all)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        # ---------------- provider / preset row ----------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        for key, label in _PROVIDERS:
            self.provider_combo.addItem(label, key)
        current = self._settings_service.get("image_provider", "mock")
        for i in range(self.provider_combo.count()):
            if self.provider_combo.itemData(i) == current:
                self.provider_combo.setCurrentIndex(i)
                break
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        row.addWidget(self.provider_combo, 1)

        row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("NONE", "none")
        for name in PRESETS:
            self.preset_combo.addItem(name, name)
        current_preset = self._settings_service.get("image_preset", "none")
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == current_preset:
                self.preset_combo.setCurrentIndex(i)
                break
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self.preset_combo, 1)
        layout.addLayout(row)

        self.external_warning = QLabel(
            "⚠ EXTERNAL PROVIDER — PROMPT LEAVES THIS MACHINE.\n"
            "Nothing is sent until you press GENERATE."
        )
        self.external_warning.setObjectName("error_hint")
        self.external_warning.setWordWrap(True)
        self.external_warning.setVisible(False)
        layout.addWidget(self.external_warning)

        # ---------------- prompts ----------------
        layout.addWidget(QLabel("Prompt:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "Describe the image to generate…"
        )
        self.prompt_edit.setMaximumHeight(90)
        layout.addWidget(self.prompt_edit)

        self.negative_label = QLabel("Negative Prompt:")
        layout.addWidget(self.negative_label)
        self.negative_edit = QPlainTextEdit()
        self.negative_edit.setMaximumHeight(60)
        self.negative_edit.setPlainText(
            self._settings_service.get("image_negative_prompt", "")
        )
        self.negative_edit.textChanged.connect(
            lambda: self._settings_service.update(
                image_negative_prompt=self.negative_edit.toPlainText()
            )
        )
        layout.addWidget(self.negative_edit)

        # ---------------- parameters grid ----------------
        self.params_grid = QGridLayout()
        self.params_grid.setHorizontalSpacing(8)
        self.params_grid.setVerticalSpacing(6)
        layout.addLayout(self.params_grid)

        # ---------------- actions ----------------
        buttons = QHBoxLayout()
        self.scene_button = QPushButton("GENERATE SCENE")
        self.scene_button.setToolTip(
            "Build a controlled prompt from the current vision scene"
        )
        self.scene_button.clicked.connect(self._on_generate_scene)
        buttons.addWidget(self.scene_button)

        self.generate_button = QPushButton("GENERATE")
        self.generate_button.setObjectName("primary")
        self.generate_button.clicked.connect(self._on_generate)
        buttons.addWidget(self.generate_button, 1)

        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.vary_button = QPushButton("IMG2IMG — VARY SELECTED")
        self.vary_button.setToolTip(
            "Image-to-image variation of the selected gallery image "
            "(only for providers that support img2img)"
        )
        self.vary_button.clicked.connect(self.vary_clicked)
        layout.addWidget(self.vary_button)

        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("value_dim")
        layout.addWidget(self.state_label)

        # ---------------- queue ----------------
        queue_title = QLabel("GENERATION QUEUE")
        queue_title.setObjectName("panel_title")
        layout.addWidget(queue_title)
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(90)
        layout.addWidget(self.queue_list)

        # ---------------- face reference ----------------
        face_title = QLabel("FACE REFERENCE (USE MY FACE)")
        face_title.setObjectName("panel_title")
        layout.addWidget(face_title)
        self.face_status_label = QLabel(
            "Not available: no configured provider supports face reference."
        )
        self.face_status_label.setObjectName("hint")
        self.face_status_label.setWordWrap(True)
        layout.addWidget(self.face_status_label)
        face_buttons = QHBoxLayout()
        self.face_upload_button = QPushButton("UPLOAD FACE")
        self.face_upload_button.clicked.connect(self.face_upload_clicked)
        self.face_remove_button = QPushButton("REMOVE FACE")
        self.face_remove_button.clicked.connect(self.face_remove_clicked)
        face_buttons.addWidget(self.face_upload_button)
        face_buttons.addWidget(self.face_remove_button)
        layout.addLayout(face_buttons)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Capabilities-driven parameter widgets
    # ------------------------------------------------------------------
    def _apply_provider_ui(self) -> None:
        """(Re-)build the parameter grid from provider capabilities."""
        while self.params_grid.count():
            item = self.params_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Drop ALL references to the widgets that are being deleted —
        # a stale attribute pointing at a deleted QObject crashes on the
        # next read (Internal C++ object already deleted). Recreated
        # below only when the new provider declares the capability.
        self.model_combo = None
        self.steps_spin = None
        self.cfg_spin = None
        self.seed_spin = None

        capabilities = self._engine.capabilities_for(
            self._current_provider_key()
        )
        row_index = 0
        if capabilities.models:
            self.params_grid.addWidget(QLabel("Model:"), row_index, 0)
            self.model_combo = QComboBox()
            self.model_combo.setEditable(True)
            self.model_combo.setEditText(
                self._settings_service.get("image_model", "")
            )
            self.model_combo.currentTextChanged.connect(
                lambda text: self._settings_service.update(image_model=text.strip())
            )
            self.params_grid.addWidget(self.model_combo, row_index, 1)
            row_index += 1

        self.size_combo = QComboBox()
        for size in capabilities.sizes:
            self.size_combo.addItem(f"{size}×{size}", size)
        current_w = str(self._settings_service.get("image_width", 512))
        for i in range(self.size_combo.count()):
            if self.size_combo.itemData(i) == current_w:
                self.size_combo.setCurrentIndex(i)
                break
        self.size_combo.currentIndexChanged.connect(self._on_size_changed)
        self.params_grid.addWidget(QLabel("Size:"), row_index, 0)
        self.params_grid.addWidget(self.size_combo, row_index, 1)
        row_index += 1

        if capabilities.steps:
            self.params_grid.addWidget(QLabel("Steps:"), row_index, 0)
            self.steps_spin = QSpinBox()
            self.steps_spin.setRange(1, 150)
            self.steps_spin.setValue(
                int(self._settings_service.get("image_steps", 20))
            )
            self.steps_spin.valueChanged.connect(
                lambda v: self._settings_service.update(image_steps=int(v))
            )
            self.params_grid.addWidget(self.steps_spin, row_index, 1)
            row_index += 1

        if capabilities.cfg:
            self.params_grid.addWidget(QLabel("Guidance (CFG):"), row_index, 0)
            self.cfg_spin = QDoubleSpinBox()
            self.cfg_spin.setRange(1.0, 30.0)
            self.cfg_spin.setSingleStep(0.5)
            self.cfg_spin.setValue(
                float(self._settings_service.get("image_cfg", 7.0))
            )
            self.cfg_spin.valueChanged.connect(
                lambda v: self._settings_service.update(image_cfg=float(v))
            )
            self.params_grid.addWidget(self.cfg_spin, row_index, 1)
            row_index += 1

        if capabilities.seed:
            self.params_grid.addWidget(QLabel("Seed:"), row_index, 0)
            seed_row = QHBoxLayout()
            self.seed_spin = QSpinBox()
            self.seed_spin.setRange(-1, 2_147_483_647)
            self.seed_spin.setSpecialValueText("random")
            self.seed_spin.setValue(
                int(self._settings_service.get("image_seed", -1))
            )
            self.seed_spin.valueChanged.connect(
                lambda v: self._settings_service.update(image_seed=int(v))
            )
            seed_row.addWidget(self.seed_spin, 1)
            self.dice_button = QPushButton("RND")
            self.dice_button.setFixedWidth(42)
            self.dice_button.setToolTip("Random seed")
            self.dice_button.clicked.connect(self._on_random_seed)
            seed_row.addWidget(self.dice_button)
            self.params_grid.addLayout(seed_row, row_index, 1)
            row_index += 1

        self.negative_label.setVisible(capabilities.negative_prompt)
        self.negative_edit.setVisible(capabilities.negative_prompt)

        # img2img gating (honest, no fake buttons).
        self.vary_button.setEnabled(capabilities.supports_img2img)
        self.vary_button.setToolTip(
            "Image-to-image variation of the selected gallery image"
            if capabilities.supports_img2img
            else "The selected provider does not support image-to-image."
        )

        # Face reference gating (honest).
        self._face_supported = capabilities.supports_face_reference
        self._update_face_reference_ui()

    # ------------------------------------------------------------------
    # Face reference state
    # ------------------------------------------------------------------
    def set_face_reference_state(self, active: bool, path_exists: bool) -> None:
        self._face_active = active
        self._face_path_exists = path_exists
        self._update_face_reference_ui()

    def _update_face_reference_ui(self) -> None:
        supported = getattr(self, "_face_supported", False)
        active = getattr(self, "_face_active", False)
        exists = getattr(self, "_face_path_exists", False)
        self.face_upload_button.setEnabled(True)  # local storage always allowed
        self.face_remove_button.setEnabled(exists)
        if not supported:
            self.face_status_label.setText(
                "Not available: no configured provider supports face "
                "reference. The photo is stored locally only."
            )
            self.face_status_label.setObjectName("hint")
        else:
            self.face_status_label.setText(
                "ACTIVE — the local face photo conditions the generation "
                "(img2img, photo never leaves this machine)."
                if active and exists
                else "Face photo stored locally — enable USE MY FACE in "
                     "the settings to condition generations."
            )
        self.face_status_label.style().unpolish(self.face_status_label)
        self.face_status_label.style().polish(self.face_status_label)

    # ------------------------------------------------------------------
    # Status / provider handling
    # ------------------------------------------------------------------
    def _on_random_seed(self) -> None:
        import random

        self.seed_spin.setValue(random.randint(0, 2_147_483_647))

    def _current_provider_key(self) -> str:
        key = self.provider_combo.itemData(self.provider_combo.currentIndex())
        return str(key) if key else "mock"

    def refresh_status(self) -> None:
        """Probe the provider in a worker thread (network I/O never runs
        on the GUI thread). Results arrive via the signal bridge."""
        provider_key = self._current_provider_key()

        def _work() -> None:
            status = self._engine.provider_status(provider_key, force=True)
            try:
                self._bridge.status.emit(status)
            except RuntimeError:
                pass  # panel teardown — receivers already gone

        threading.Thread(
            target=_work, name="image-status-probe", daemon=True
        ).start()

    def set_status(self, status: dict) -> None:
        """Render an already-probed status (non-blocking, GUI thread)."""
        self._on_status(status)

    def _on_status(self, status: dict) -> None:
        if status["status"] == "online":
            self.status_label.setText(
                f"IMAGE GENERATION: ● ONLINE — {status['detail']}"
            )
        elif status["status"] == "mock":
            self.status_label.setText(
                f"IMAGE GENERATION: ● MOCK — {status['detail']}"
            )
        elif status["status"] == "offline":
            self.status_label.setText(
                f"IMAGE GENERATION: ● OFFLINE — {status['detail']}"
            )
            self.status_label.setObjectName("error_hint")
        elif status["status"] == "unavailable":
            self.status_label.setText("IMAGE GENERATION: ● UNAVAILABLE")
            self.status_label.setObjectName("error_hint")
        else:
            self.status_label.setText("IMAGE GENERATION: ● READY (configured)")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._refresh_models_async()

    def _refresh_models_async(self) -> None:
        def _work() -> None:
            models = self._engine.list_models(self._current_provider_key())
            try:
                self._bridge.models.emit(models)
            except RuntimeError:
                pass  # panel teardown — receivers already gone

        threading.Thread(target=_work, name="image-models", daemon=True).start()

    def _on_models(self, models: list[str]) -> None:
        combo = getattr(self, "model_combo", None)
        if combo is None or not models:
            return
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        for name in models:
            combo.addItem(name)
        if current in models:
            combo.setCurrentText(current)
        else:
            combo.setEditText(models[0] if models else "")
        combo.blockSignals(False)

    def _on_refresh_all(self) -> None:
        self.refresh_status()
        self._refresh_queue_list()

    def _on_provider_changed(self, index: int) -> None:
        key = self.provider_combo.itemData(index)
        if not key:
            return
        self._settings_service.update(image_provider=key)
        self.external_warning.setVisible(key == "external")
        self._apply_provider_ui()
        self.refresh_status()

    def _on_preset_changed(self, index: int) -> None:
        key = self.preset_combo.itemData(index)
        if key is None:
            return
        self._settings_service.update(image_preset=key)
        if key != "none" and self.prompt_edit.toPlainText().strip():
            effective = apply_preset(
                key,
                self.prompt_edit.toPlainText(),
                negative_prompt=self.negative_edit.toPlainText(),
                default_steps=int(self._settings_service.get("image_steps", 20)),
                default_cfg=float(self._settings_service.get("image_cfg", 7.0)),
            )
            self.state_label.setText(
                f"PRESET {key}: {effective.steps} steps, CFG {effective.cfg} "
                f"(applied on generate)"
            )

    def _on_size_changed(self, index: int) -> None:
        size = self.size_combo.itemData(index)
        if size:
            self._settings_service.update(
                image_width=int(size), image_height=int(size)
            )

    # ------------------------------------------------------------------
    # Generation (queue-based)
    # ------------------------------------------------------------------
    def _current_params(self) -> dict:
        params: dict = {}
        steps_spin = getattr(self, "steps_spin", None)
        cfg_spin = getattr(self, "cfg_spin", None)
        seed_spin = getattr(self, "seed_spin", None)
        model_combo = getattr(self, "model_combo", None)
        if steps_spin is not None:
            params["steps"] = steps_spin.value()
        if cfg_spin is not None:
            params["cfg"] = cfg_spin.value()
        if seed_spin is not None:
            params["seed"] = seed_spin.value()
        if model_combo is not None:
            params["model"] = model_combo.currentText().strip()
        size = int(self.size_combo.itemData(self.size_combo.currentIndex()))
        return {**params,
                "width": size,
                "height": size,
                "negative_prompt": self.negative_edit.toPlainText()
                if self.negative_edit.isVisible() else "",
                "preset": str(self.preset_combo.itemData(
                    self.preset_combo.currentIndex())),
                "provider_key": self._current_provider_key()}

    def _on_generate_scene(self) -> None:
        snapshot = self._snapshot_provider()
        prompt = build_scene_prompt(snapshot)
        if prompt is None:
            self.state_label.setText(
                "No vision data to build a scene prompt from."
            )
            return
        self.prompt_edit.setPlainText(prompt)

    def _on_generate(self) -> None:
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            self.state_label.setText("Enter a prompt first.")
            return
        params = self._current_params()
        job = self._engine.enqueue(prompt, **params)
        self.state_label.setText(f"QUEUED — job #{job.id}")
        self._refresh_queue_list()

    def _on_cancel(self) -> None:
        jobs = self._engine.queue.active_jobs()
        generating = [j for j in jobs if j.status == GENERATING]
        if generating:
            self._engine.cancel(generating[0].id)
            self.state_label.setText(
                f"CANCEL REQUESTED — job #{generating[0].id}"
            )
        else:
            queued = [j for j in jobs if j.status == "QUEUED"]
            if queued:
                self._engine.cancel(queued[0].id)
                self.state_label.setText("QUEUED JOB CANCELLED")
            else:
                self.state_label.setText("NOTHING TO CANCEL")
        self._refresh_queue_list()

    def on_job_status(self, job: GenerationJob) -> None:
        """GUI-thread job status update (called via the signal bridge)."""
        self._refresh_queue_list()
        if job.status == COMPLETED:
            duration = (
                f", {job.duration_ms:.0f} ms" if job.duration_ms else ""
            )
            self.state_label.setText(f"DONE — job #{job.id}{duration}")
        elif job.status == FAILED:
            provider_name = _PROVIDER_NAMES.get(job.provider_key, job.provider_key)
            friendly = format_provider_error(provider_name, job.error or "")
            self.state_label.setText(
                f"FAILED — job #{job.id}\n{friendly}"
            )
            self.state_label.setToolTip(job.error or "")
        elif job.status == GENERATING:
            self.state_label.setText(f"{format_job_status(job)}")
        elif job.status == "CANCELLED":
            self.state_label.setText(f"CANCELLED — job #{job.id}")

    def _refresh_queue_list(self) -> None:
        self.queue_list.clear()
        for job in self._engine.queue.active_jobs(limit=12):
            text = (
                f"{format_job_status(job)} — {job.prompt[:60]}"
            )
            self.queue_list.addItem(text)

