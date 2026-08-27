"""SYSTEM panel (v1.4): providers, capabilities, diagnostics, privacy.

Structure:
    SYSTEM STATUS      — inline diagnostics (PASS/WARN/FAIL/UNAVAILABLE)
    VISION PERFORMANCE — mode + delegate (real reports only)
    LLM PROVIDER       — provider/model/base URL/temperature/timeout
    IMAGE PROVIDER     — SD WebUI / API URLs
    STORAGE & PRIVACY  — data dir, counts, API-key state, capabilities,
                         latency, last error

Honest by contract: provider status is never "online" when it isn't,
hardware status is never invented, and API keys are never entered or
shown here — they come from the AI_VISION_LAB_API_KEY environment
variable only.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ai.engine import AIVisionEngine
from app.config.settings import SettingsService
from app.image.engine import ImageGenerationEngine
from app.ui.icons import refresh_icon
from app.ui.components import SectionHeader, StatusBadge
from app.utils.logging_setup import get_logger

log = get_logger("ui.system_panel")

_LLM_PROVIDERS = (
    ("ollama", "Ollama (local)"),
    ("openai_compatible", "OpenAI Compatible"),
    ("mock", "Mock (dev fallback)"),
)


class _Bridge(QObject):
    models = Signal(list)
    status = Signal(object)
    diagnostics = Signal(object)  # DiagnosticReport


class SystemPanel(QWidget):
    """Provider configuration + status + diagnostics."""

    #: Settings that also need runtime application (vision mode).
    setting_changed = Signal(str, object)

    def __init__(
        self,
        settings_service: SettingsService,
        ai_engine: AIVisionEngine,
        image_engine: ImageGenerationEngine,
        diagnostics_callback: Optional[Callable[[Callable], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._ai_engine = ai_engine
        self._image_engine = image_engine
        self._diagnostics_callback = diagnostics_callback
        self._bridge = _Bridge()
        self._bridge.models.connect(self._on_models)
        self._bridge.status.connect(self._on_status)
        self._bridge.diagnostics.connect(self._on_diagnostics)
        self._build_ui()
        self.refresh_status()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        settings = self._settings_service.settings

        # ---------------- SYSTEM STATUS (diagnostics) ----------------
        diag_card = QFrame()
        diag_card.setObjectName("panel")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(14, 12, 14, 12)
        diag_layout.setSpacing(8)
        diag_header = QHBoxLayout()
        diag_header.addWidget(SectionHeader("SYSTEM STATUS"))
        diag_header.addStretch(1)
        self.diagnostics_button = QPushButton("RUN SYSTEM CHECK")
        self.diagnostics_button.clicked.connect(self._run_diagnostics)
        diag_header.addWidget(self.diagnostics_button)
        diag_layout.addLayout(diag_header)
        self.diagnostics_summary = QLabel(
            "Run the system check to verify Python, dependencies, models, "
            "camera, GPU, providers and storage."
        )
        self.diagnostics_summary.setObjectName("hint")
        self.diagnostics_summary.setWordWrap(True)
        diag_layout.addWidget(self.diagnostics_summary)
        self._diag_badges: dict[str, StatusBadge] = {}
        diag_grid = QHBoxLayout()
        diag_grid.setSpacing(14)
        for name in ("PYTHON", "DEPENDENCIES", "MODELS", "CAMERA", "GPU",
                     "OLLAMA", "SD WEBUI", "STORAGE"):
            row = QVBoxLayout()
            row.setSpacing(2)
            label = QLabel(name)
            label.setObjectName("kpi_label")
            row.addWidget(label)
            badge = StatusBadge()
            badge.set_status("idle", "—")
            self._diag_badges[name] = badge
            row.addWidget(badge)
            diag_grid.addLayout(row)
        diag_grid.addStretch(1)
        diag_layout.addLayout(diag_grid)
        layout.addWidget(diag_card)

        # ---------------- GENERAL (behaviour) ----------------
        switches_card = QFrame()
        switches_card.setObjectName("panel")
        switches_layout = QVBoxLayout(switches_card)
        switches_layout.setContentsMargins(14, 12, 14, 12)
        general_header = QHBoxLayout()
        general_header.addWidget(SectionHeader("GENERAL"))
        general_header.addStretch(1)
        self.reset_button = QPushButton("RESET ALL SETTINGS")
        self.reset_button.setObjectName("ghost")
        self.reset_button.setToolTip(
            "Restore every setting to its documented default "
            "(providers, camera, vision, privacy)."
        )
        self.reset_button.clicked.connect(self._on_reset_settings)
        general_header.addWidget(self.reset_button)
        switches_layout.addLayout(general_header)
        switches = QGridLayout()
        switches.setHorizontalSpacing(12)
        switches.setVerticalSpacing(6)
        self.ai_enabled_check = QCheckBox("AI Enabled")
        self.ai_enabled_check.setChecked(settings.ai_enabled)
        self.ai_enabled_check.toggled.connect(
            lambda v: self._settings_service.update(ai_enabled=v)
        )
        switches.addWidget(self.ai_enabled_check, 0, 0)
        self.offline_check = QCheckBox("Offline Mode")
        self.offline_check.setChecked(settings.offline_mode)
        self.offline_check.toggled.connect(
            lambda v: self._settings_service.update(offline_mode=v)
        )
        switches.addWidget(self.offline_check, 0, 1)
        self.auto_summary_check = QCheckBox("Auto Summary")
        self.auto_summary_check.setChecked(settings.vision_auto_summary)
        self.auto_summary_check.toggled.connect(
            lambda v: self._settings_service.update(vision_auto_summary=v)
        )
        switches.addWidget(self.auto_summary_check, 1, 0)
        self.image_enabled_check = QCheckBox("Image Gen Enabled")
        self.image_enabled_check.setChecked(settings.image_generation_enabled)
        self.image_enabled_check.toggled.connect(
            lambda v: self._settings_service.update(image_generation_enabled=v)
        )
        switches.addWidget(self.image_enabled_check, 1, 1)
        self.voice_check = QCheckBox("Read Answers Aloud")
        self.voice_check.setChecked(settings.voice_enabled)
        self.voice_check.setToolTip(
            "Speak every AI answer via the system voice (only when a "
            "voice is detected — answers stay on this machine)."
        )
        self.voice_check.toggled.connect(
            lambda v: self._settings_service.update(voice_enabled=v)
        )
        switches.addWidget(self.voice_check, 2, 0)
        self.voice_hint = QLabel("Voice: no voice detected on this machine.")
        self.voice_hint.setObjectName("hint")
        switches.addWidget(self.voice_hint, 2, 1)
        self.extensions_check = QCheckBox("Load local extensions")
        self.extensions_check.setChecked(settings.extensions_enabled)
        self.extensions_check.setToolTip(
            "Load data/extensions/*.py on the next start "
            "(opt-in, isolated, never remote)."
        )
        self.extensions_check.toggled.connect(
            lambda v: self._settings_service.update(extensions_enabled=v)
        )
        switches.addWidget(self.extensions_check, 3, 0)
        extensions_hint = QLabel("Applies after restart.")
        extensions_hint.setObjectName("hint")
        switches.addWidget(extensions_hint, 3, 1)
        switches_layout.addLayout(switches)
        layout.addWidget(switches_card)

        # ---------------- Vision performance ----------------
        vision_card = QFrame()
        vision_card.setObjectName("panel")
        vision_layout = QVBoxLayout(vision_card)
        vision_layout.setContentsMargins(14, 12, 14, 12)
        vision_layout.addWidget(SectionHeader("VISION PERFORMANCE"))

        vision_grid = QGridLayout()
        vision_grid.setHorizontalSpacing(8)
        vision_grid.addWidget(QLabel("Mode:"), 0, 0)
        self.vision_mode_combo = QComboBox()
        for key, label in (("quality", "QUALITY"),
                           ("balanced", "BALANCED"),
                           ("performance", "PERFORMANCE")):
            self.vision_mode_combo.addItem(label, key)
        for i in range(self.vision_mode_combo.count()):
            if self.vision_mode_combo.itemData(i) == settings.vision_mode:
                self.vision_mode_combo.setCurrentIndex(i)
                break
        self.vision_mode_combo.currentIndexChanged.connect(self._on_vision_mode)
        vision_grid.addWidget(self.vision_mode_combo, 0, 1)

        vision_grid.addWidget(QLabel("Delegate:"), 1, 0)
        self.delegate_combo = QComboBox()
        for key, label in (("cpu", "CPU (stable)"),
                           ("gpu", "GPU (auto fallback)")):
            self.delegate_combo.addItem(label, key)
        for i in range(self.delegate_combo.count()):
            if self.delegate_combo.itemData(i) == settings.vision_delegate:
                self.delegate_combo.setCurrentIndex(i)
                break
        self.delegate_combo.currentIndexChanged.connect(self._on_delegate)
        vision_grid.addWidget(self.delegate_combo, 1, 1)
        self.delegate_hint = QLabel(
            "Delegate changes apply after restart."
        )
        self.delegate_hint.setObjectName("hint")
        vision_grid.addWidget(self.delegate_hint, 2, 0, 1, 2)
        self.delegates_label = QLabel("")
        self.delegates_label.setObjectName("hint")
        self.delegates_label.setWordWrap(True)
        vision_grid.addWidget(self.delegates_label, 3, 0, 1, 2)
        vision_layout.addLayout(vision_grid)
        layout.addWidget(vision_card)

        # ---------------- LLM section ----------------
        llm_card = QFrame()
        llm_card.setObjectName("panel")
        llm_layout = QVBoxLayout(llm_card)
        llm_layout.setContentsMargins(14, 12, 14, 12)
        llm_layout.setSpacing(8)
        llm_header = QHBoxLayout()
        llm_header.addWidget(SectionHeader("AI PROVIDER"))
        llm_header.addStretch(1)
        self.llm_status = QLabel("LLM: —")
        self.llm_status.setObjectName("hint")
        llm_header.addWidget(self.llm_status)
        llm_layout.addLayout(llm_header)

        llm_grid = QGridLayout()
        llm_grid.setHorizontalSpacing(8)
        llm_grid.setVerticalSpacing(6)

        llm_grid.addWidget(QLabel("Provider:"), 0, 0)
        self.llm_provider_combo = QComboBox()
        for key, label in _LLM_PROVIDERS:
            self.llm_provider_combo.addItem(label, key)
        for i in range(self.llm_provider_combo.count()):
            if self.llm_provider_combo.itemData(i) == settings.llm_provider:
                self.llm_provider_combo.setCurrentIndex(i)
                break
        self.llm_provider_combo.currentIndexChanged.connect(self._on_llm_provider)
        llm_grid.addWidget(self.llm_provider_combo, 0, 1)

        llm_grid.addWidget(QLabel("Model:"), 1, 0)
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setEditText(settings.llm_model or "llama3")
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_row.addWidget(self.model_combo, 1)
        self.model_refresh = QPushButton("⟳")
        self.model_refresh.setFixedWidth(36)
        refresh_icon(self.model_refresh, "Detect models (Ollama)")
        self.model_refresh.clicked.connect(self._refresh_models)
        model_row.addWidget(self.model_refresh)
        llm_grid.addLayout(model_row, 1, 1)

        llm_grid.addWidget(QLabel("Base URL:"), 2, 0)
        self.base_url_edit = QLineEdit(settings.llm_base_url)
        self.base_url_edit.editingFinished.connect(
            lambda: self._settings_service.update(
                llm_base_url=self.base_url_edit.text().strip() or settings.llm_base_url
            )
        )
        llm_grid.addWidget(self.base_url_edit, 2, 1)

        llm_grid.addWidget(QLabel("Temperature:"), 3, 0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(settings.llm_temperature)
        self.temperature_spin.valueChanged.connect(
            lambda v: self._settings_service.update(llm_temperature=float(v))
        )
        llm_grid.addWidget(self.temperature_spin, 3, 1)

        llm_grid.addWidget(QLabel("Timeout (s):"), 4, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(settings.llm_timeout)
        self.timeout_spin.valueChanged.connect(
            lambda v: self._settings_service.update(llm_timeout=int(v))
        )
        llm_grid.addWidget(self.timeout_spin, 4, 1)
        llm_layout.addLayout(llm_grid)
        layout.addWidget(llm_card)

        # ---------------- Image section ----------------
        image_card = QFrame()
        image_card.setObjectName("panel")
        image_layout = QVBoxLayout(image_card)
        image_layout.setContentsMargins(14, 12, 14, 12)
        image_layout.setSpacing(8)
        image_header = QHBoxLayout()
        image_header.addWidget(SectionHeader("IMAGE PROVIDER"))
        image_header.addStretch(1)
        self.image_status = QLabel("IMAGE: —")
        self.image_status.setObjectName("hint")
        image_header.addWidget(self.image_status)
        image_layout.addLayout(image_header)

        image_grid = QGridLayout()
        image_grid.setHorizontalSpacing(8)
        image_grid.addWidget(QLabel("SD WebUI URL:"), 0, 0)
        self.sdwebui_url_edit = QLineEdit(settings.sdwebui_base_url)
        self.sdwebui_url_edit.editingFinished.connect(
            lambda: self._settings_service.update(
                sdwebui_base_url=self.sdwebui_url_edit.text().strip()
                or settings.sdwebui_base_url
            )
        )
        image_grid.addWidget(self.sdwebui_url_edit, 0, 1)

        image_grid.addWidget(QLabel("ComfyUI URL:"), 1, 0)
        self.comfyui_url_edit = QLineEdit(settings.comfyui_base_url)
        self.comfyui_url_edit.editingFinished.connect(
            lambda: self._settings_service.update(
                comfyui_base_url=self.comfyui_url_edit.text().strip()
                or settings.comfyui_base_url
            )
        )
        image_grid.addWidget(self.comfyui_url_edit, 1, 1)

        image_grid.addWidget(QLabel("Images API URL:"), 2, 0)
        self.image_base_url_edit = QLineEdit(settings.image_base_url)
        self.image_base_url_edit.editingFinished.connect(
            lambda: self._settings_service.update(
                image_base_url=self.image_base_url_edit.text().strip()
                or settings.image_base_url
            )
        )
        image_grid.addWidget(self.image_base_url_edit, 2, 1)
        image_layout.addLayout(image_grid)

        key_hint = QLabel(
            "API key: environment variable AI_VISION_LAB_API_KEY "
            "(never stored, never logged)."
        )
        key_hint.setObjectName("hint")
        key_hint.setWordWrap(True)
        image_layout.addWidget(key_hint)
        layout.addWidget(image_card)

        # ---------------- Storage + privacy ---------------- #
        storage_card = QFrame()
        storage_card.setObjectName("panel")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(14, 12, 14, 12)
        storage_header = QHBoxLayout()
        storage_header.addWidget(SectionHeader("STORAGE & PRIVACY"))
        storage_header.addStretch(1)
        self.refresh_button = QPushButton("REFRESH STATUS")
        self.refresh_button.clicked.connect(self.refresh_status)
        storage_header.addWidget(self.refresh_button)
        storage_layout.addLayout(storage_header)
        self.storage_label = QLabel("")
        self.storage_label.setObjectName("hint")
        self.storage_label.setWordWrap(True)
        storage_layout.addWidget(self.storage_label)
        layout.addWidget(storage_card)

        # ---------------- Hardware reports (Phase 25) ----------------
        reports_card = QFrame()
        reports_card.setObjectName("panel")
        reports_layout = QVBoxLayout(reports_card)
        reports_layout.setContentsMargins(14, 12, 14, 12)
        reports_layout.setSpacing(8)
        reports_header = QHBoxLayout()
        reports_header.addWidget(SectionHeader("HARDWARE REPORTS"))
        reports_header.addStretch(1)
        self.reports_button = QPushButton("LOAD REPORTS")
        self.reports_button.setToolTip(
            "Read the acceptance/smoke/stability JSON reports from the "
            "project folder and show the verification matrix — real "
            "data only, stale or foreign reports are excluded."
        )
        self.reports_button.setAccessibleName("Load hardware reports")
        self.reports_button.clicked.connect(self._on_load_reports)
        reports_header.addWidget(self.reports_button)
        reports_layout.addLayout(reports_header)
        self.reports_summary = QLabel(
            "No reports loaded. Run the hardware acceptance on this "
            "machine (README: 'Real Hardware Acceptance') — the real "
            "verification matrix appears here."
        )
        self.reports_summary.setObjectName("hint")
        self.reports_summary.setWordWrap(True)
        reports_layout.addWidget(self.reports_summary)
        self._report_badges_widget = QWidget()
        self._report_badges_layout = QVBoxLayout(self._report_badges_widget)
        self._report_badges_layout.setContentsMargins(0, 0, 0, 0)
        self._report_badges_layout.setSpacing(2)
        badges_scroll = QScrollArea()
        badges_scroll.setWidgetResizable(True)
        badges_scroll.setFrameShape(QFrame.Shape.NoFrame)
        badges_scroll.setMaximumHeight(200)
        badges_scroll.setWidget(self._report_badges_widget)
        reports_layout.addWidget(badges_scroll)
        self._report_badges: dict[str, StatusBadge] = {}
        layout.addWidget(reports_card)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Hardware reports (Phase 25)
    # ------------------------------------------------------------------
    def _on_load_reports(self) -> None:
        from pathlib import Path

        self.load_reports_from(Path.cwd())

    def load_reports_from(self, directory) -> None:
        """Render the newest usable acceptance report (honest).

        Stale (> 30 days), version-mismatched, foreign-machine and
        secret-tainted reports never count; conflicting reports are
        listed as warnings. Without usable reports the panel says so —
        missing data is never turned into a PASS.
        """
        from pathlib import Path

        from app.utils.report_importer import (
            find_conflicts,
            load_reports,
            usable_evidence,
        )

        self._clear_report_badges()
        entries = load_reports(Path(directory), expected_version=None)
        usable = usable_evidence(entries)
        if not usable:
            self.reports_summary.setText(
                "No fresh usable reports found in the project folder. "
                "Run the acceptance on this machine — the verification "
                "matrix appears here (real data only)."
            )
            return
        # Prefer the acceptance report (full matrix); fall back to smoke.
        chosen = None
        for entry in usable:
            data = entry["data"] or {}
            if isinstance(data.get("verification_matrix"), dict):
                chosen = entry
                break
        if chosen is None:
            chosen = usable[0]
        data = chosen["data"] or {}
        matrix = data.get("verification_matrix") or {}
        verdict = (data.get("final_verdict") or {}).get("verdict", "?")
        version = chosen["version"] or "?"
        warnings: list[str] = []
        conflicts = find_conflicts(entries)
        if conflicts:
            warnings.append(
                "conflicting reports: " + "; ".join(conflicts[:3])
            )
        stale = [e for e in entries if e["stale"]]
        if stale:
            warnings.append(
                f"{len(stale)} stale/foreign report(s) ignored"
            )
        self.reports_summary.setText(
            f"{Path(chosen['path']).name} · app v{version} · "
            f"verdict {verdict}"
            + (("\n" + "\n".join(warnings)) if warnings else "")
        )
        for name, item in sorted(matrix.items()):
            status = str(item.get("status", "UNTESTABLE"))
            result = item.get("result")
            if status == "REAL VERIFIED":
                badge_status = "ready" if result == "passed" else "error"
                text = "PASS" if result == "passed" else "FAIL"
            elif status in ("MOCK VERIFIED", "STUB VERIFIED"):
                badge_status = "mock"
                text = status.split(" ")[0]
            else:
                badge_status = "untestable"
                text = "—"
            badge = StatusBadge()
            badge.set_status(badge_status, text)
            badge.setToolTip(
                f"{name}: {item.get('evidence', '')[:160]}"
            )
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            label = QLabel(name)
            label.setObjectName("kpi_label")
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(badge)
            wrap = QWidget()
            wrap.setLayout(row)
            self._report_badges_layout.addWidget(wrap)
            self._report_badges[name] = badge

    def _clear_report_badges(self) -> None:
        while self._report_badges_layout.count():
            item = self._report_badges_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._report_badges.clear()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def _run_diagnostics(self) -> None:
        self.diagnostics_summary.setText("Running system check…")
        if self._diagnostics_callback is None:
            from app.diagnostics import run_diagnostics

            report = run_diagnostics()
            self._on_diagnostics(report)
            return
        # Emit via the queued signal so the worker never touches widgets.
        self._diagnostics_callback(self._bridge.diagnostics.emit)

    def _on_diagnostics(self, report) -> None:
        counts = (
            f"{sum(1 for c in report.checks if c.status == 'PASS')} pass · "
            f"{sum(1 for c in report.checks if c.status == 'WARN')} warn · "
            f"{sum(1 for c in report.checks if c.status == 'FAIL')} fail · "
            f"{sum(1 for c in report.checks if c.status == 'UNAVAILABLE')} "
            "unavailable"
        )
        self.diagnostics_summary.setText(
            "SYSTEM CHECK: " + counts
        )
        for check in report.checks:
            # Diagnostics name -> badge key (both stay stable on every
            # machine: the 9-check contract is an invariant).
            badge = self._diag_badges.get(
                {"MODEL FILES": "MODELS"}.get(check.name, check.name)
            )
            if badge is None:
                continue
            status = {
                "PASS": "ready",
                "WARN": "mock",
                "FAIL": "error",
                "UNAVAILABLE": "untestable",
            }.get(check.status, "idle")
            badge.set_status(status, check.status)
            badge.setToolTip(
                f"{check.detail}\nFix: {check.fix}" if check.fix
                else check.detail
            )

    # ------------------------------------------------------------------
    # Status + model detection
    # ------------------------------------------------------------------
    def refresh_status(self) -> None:
        """Probe both providers in a worker thread (network I/O never
        runs on the GUI thread). Results arrive via the signal bridge."""
        def _work() -> None:
            llm = self._ai_engine.provider_status(force=True)
            image = self._image_engine.provider_status(force=True)
            try:
                self._bridge.status.emit((llm, image))
            except RuntimeError:
                pass  # panel teardown — receivers already gone

        threading.Thread(
            target=_work, name="system-status-probe", daemon=True
        ).start()

    def set_statuses(self, llm: dict, image: dict) -> None:
        """Render already-probed statuses (non-blocking, GUI thread)."""
        self._on_status((llm, image))

    def _on_status(self, payload: tuple[dict, dict]) -> None:
        llm, image = payload
        if llm["status"] == "online":
            self.llm_status.setText(f"LLM ● ONLINE — {llm['detail']}")
            self.llm_status.setObjectName("hint")
        elif llm["status"] == "mock":
            self.llm_status.setText(f"LLM ● MOCK — {llm['detail']}")
            self.llm_status.setObjectName("hint")
        else:
            self.llm_status.setText(
                f"LLM ● OFFLINE / CONFIGURED — {llm['detail']}"
            )
            self.llm_status.setObjectName("error_hint")
        self.llm_status.style().unpolish(self.llm_status)
        self.llm_status.style().polish(self.llm_status)

        if image["status"] == "mock":
            self.image_status.setText(
                f"IMAGE GENERATION ● MOCK — {image['detail']}"
            )
        elif image["status"] == "unavailable":
            self.image_status.setText(
                f"IMAGE GENERATION ● UNAVAILABLE — {image['detail']}"
            )
            self.image_status.setObjectName("error_hint")
        else:
            self.image_status.setText(
                f"IMAGE GENERATION ● READY — {image['detail']}"
            )
        self.image_status.style().unpolish(self.image_status)
        self.image_status.style().polish(self.image_status)

    def _refresh_models(self) -> None:
        def _work() -> None:
            models = self._ai_engine.list_ollama_models()
            try:
                self._bridge.models.emit(models)
            except RuntimeError:
                pass  # panel teardown — receivers already gone

        threading.Thread(target=_work, name="ollama-models", daemon=True).start()

    def _on_models(self, models: list[str]) -> None:
        current = self.model_combo.currentText()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for name in models:
            self.model_combo.addItem(name)
        if models:
            if current in models:
                self.model_combo.setCurrentText(current)
            else:
                self.model_combo.setCurrentText(models[0])
                self._settings_service.update(llm_model=models[0])
        else:
            self.model_combo.setEditText(current)
        self.model_combo.blockSignals(False)

    def _on_llm_provider(self, index: int) -> None:
        key = self.llm_provider_combo.itemData(index)
        if key:
            self._settings_service.update(llm_provider=key)
        self.refresh_status()

    def _on_model_changed(self, text: str) -> None:
        self._settings_service.update(llm_model=text.strip())

    def set_storage_info(
        self,
        data_directory: str,
        generated_count: int,
        uploads_count: int,
        key_configured: bool,
        image_capabilities: str = "",
        image_last_duration_ms=None,
        image_last_error: str = "",
        llm_last_duration_ms=None,
    ) -> None:
        """Storage/privacy + provider-management block (real values only)."""
        key = "set (environment)" if key_configured else "not set"
        lines = [
            f"Data: {data_directory}",
            f"Generated images: {generated_count} · Uploads: {uploads_count}",
            f"API key: {key} · All processing local unless an EXTERNAL "
            "provider is explicitly used.",
        ]
        if image_capabilities:
            lines.append(f"Image provider capabilities: {image_capabilities}")
        if image_last_duration_ms is not None:
            lines.append(
                f"Last generation: {image_last_duration_ms:.0f} ms"
            )
        if image_last_error:
            lines.append(f"Last generation error: {image_last_error[:80]}")
        if llm_last_duration_ms is not None:
            lines.append(f"Last LLM call: {llm_last_duration_ms:.0f} ms")
        self.storage_label.setText("\n".join(lines))

    def _on_reset_settings(self) -> None:
        """RESET ALL SETTINGS: confirm, restore defaults, notify MainWindow."""
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Reset all settings")
        box.setText("Restore every setting to its documented default?")
        box.setInformativeText(
            "Providers, camera, vision modules, privacy and performance "
            "settings are reset. Generated images and uploads are kept."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._settings_service.reset()
        self.sync_from_settings()
        self.setting_changed.emit("__reset__", None)

    def sync_from_settings(self) -> None:
        """Re-read every control from the (possibly reset) settings."""
        settings = self._settings_service.settings
        controls = (
            (self.ai_enabled_check, settings.ai_enabled),
            (self.offline_check, settings.offline_mode),
            (self.auto_summary_check, settings.vision_auto_summary),
            (self.image_enabled_check, settings.image_generation_enabled),
            (self.voice_check, settings.voice_enabled),
        )
        for checkbox, value in controls:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(value))
            checkbox.blockSignals(False)
        for combo, key in ((self.vision_mode_combo, settings.vision_mode),
                           (self.delegate_combo, settings.vision_delegate),
                           (self.llm_provider_combo, settings.llm_provider)):
            combo.blockSignals(True)
            for i in range(combo.count()):
                if combo.itemData(i) == key:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)
        self.base_url_edit.blockSignals(True)
        self.base_url_edit.setText(settings.llm_base_url)
        self.base_url_edit.blockSignals(False)
        self.temperature_spin.blockSignals(True)
        self.temperature_spin.setValue(settings.llm_temperature)
        self.temperature_spin.blockSignals(False)
        self.timeout_spin.blockSignals(True)
        self.timeout_spin.setValue(settings.llm_timeout)
        self.timeout_spin.blockSignals(False)
        self.sdwebui_url_edit.blockSignals(True)
        self.sdwebui_url_edit.setText(settings.sdwebui_base_url)
        self.sdwebui_url_edit.blockSignals(False)
        self.comfyui_url_edit.blockSignals(True)
        self.comfyui_url_edit.setText(settings.comfyui_base_url)
        self.comfyui_url_edit.blockSignals(False)
        self.image_base_url_edit.blockSignals(True)
        self.image_base_url_edit.setText(settings.image_base_url)
        self.image_base_url_edit.blockSignals(False)
        self.extensions_check.blockSignals(True)
        self.extensions_check.setChecked(bool(settings.extensions_enabled))
        self.extensions_check.blockSignals(False)

    def _on_vision_mode(self, index: int) -> None:
        key = self.vision_mode_combo.itemData(index)
        if key:
            self._settings_service.update(vision_mode=key)
            self.setting_changed.emit("vision_mode", key)

    def _on_delegate(self, index: int) -> None:
        key = self.delegate_combo.itemData(index)
        if key:
            self._settings_service.update(vision_delegate=key)

    def set_voice_status(self, status: str, detail: str = "") -> None:
        """Capability-gate the read-aloud toggle (no fake toggles)."""
        if status in ("real", "mock"):
            self.voice_check.setEnabled(True)
            self.voice_hint.setText(
                f"Voice: {status.upper()}"
                + (f" — {detail}" if detail else "")
            )
        else:
            self.voice_check.setEnabled(False)
            self.voice_check.setChecked(False)
            self.voice_hint.setText(
                "Voice: no voice detected on this machine "
                "(system TTS not found)."
            )

    def set_delegate_summary(self, summary: dict[str, str]) -> None:
        """Show the delegate each loaded module actually reports (honest).

        Only real reports are shown — never an assumed GPU status.
        """
        if not summary:
            self.delegates_label.setText("")
            return
        parts = [
            f"{key}: {message.replace('delegate: ', '')}"
            for key, message in sorted(summary.items())
        ]
        self.delegates_label.setText("Active delegates — " + " · ".join(parts))
