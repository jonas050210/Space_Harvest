"""Main application window (studio layout — v2.1 command center).

    ┌──────────────────────────────────────────────────────────────────┐
    │ AI VISION LAB v2.1.1        GPU · LLM MOCK · IMG MOCK   ● LIVE  │
    ├────────┬─────────────────────────────────────────────────────────┤
    │ NAV    │  HOME / VISION / CREATE / ANALYZE / GALLERY /           │
    │ RAIL   │  SYSTEM / ASSISTANT / INSIGHTS  (Ctrl+1..8)             │
    ├────────┴─────────────────────────────────────────────────────────┤
    │ FPS | Frame Time | Camera | Resolution | CPU | RAM               │
    │ QUEUE: … | EVENT: … | LLM ● | IMG ●                              │
    └──────────────────────────────────────────────────────────────────┘

Pages:

* HOME      — hero status, first-run onboarding (6 steps), status cards,
              quick actions, recent activity/results, system health.
* VISION    — left: camera + vision controls · center: live feed with
              minimalist HUD + live state cards · right: scene capture,
              object selection, LIVE INSPECTOR. RECORD / SNAPSHOT.
* CREATE    — left: prompt/settings · center: large preview · right:
              result information; actions ANALYZE / REGENERATE / VARY /
              COMPARE / SAVE.
* ANALYZE   — large image on top, structured analysis + feedback below.
* GALLERY   — asset-library grid + detail pane.
* SYSTEM    — providers, capabilities, latency, diagnostics.
* ASSISTANT — chat with quick commands (English; German aliases work).
* INSIGHTS  — session analytics (heatmap, pulse, recap).

The window stays responsive during capture: frames are analysed in a
worker thread and polled via QTimers (30 Hz frame pull, 1 Hz system
stats). The event loop itself never touches the camera. Delegates and
generation status are cached at 1–2 Hz so UI polish never costs vision
performance.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.engine import AIVisionEngine
from app.ai.events import EventType
from app.ai.reactions import ReactionEngine
from app.analysis.engine import ImageAnalysisEngine
from app.analysis.feedback import refine_prompt
from app.camera.camera_manager import CameraInfo
from app.config.calibration import CalibrationProfile
from app.config.settings import SettingsService
from app.core.types import FeedbackEntry, ImageAnalysisResult
from app.image.engine import ImageGenerationEngine
from app.image.queue import GENERATING, format_job_status
from app.image.storage import ImageRecord, ImageStore
from app.ui.calibration_overlay import CalibrationOverlay
from app.ui.command_center import CommandCenter
from app.ui.components import (
    EmptyState,
    MetricCard,
    NavButton,
    SectionHeader,
    StatusBadge,
)
from app.ui.controller import CameraController
from app.ui.hud import HudOverlay
from app.ui.theme import apply_theme
from app.ui.toast import ToastManager
from app.ui.widgets import (
    AIPanel,
    InsightsPanel,
    ActivityBar,
    AnalysisPanel,
    CameraPanel,
    GalleryPanel,
    GazePanel,
    HeaderBar,
    ImageAnalysisPanel,
    ImagePanel,
    InspectorPanel,
    LiveStatePanel,
    ModulesPanel,
    PreviewWorkspace,
    StatusPanel,
    SystemPanel,
    VideoWidget,
    VisionControlsPanel,
    VisionPanel,
)
from PySide6.QtGui import QKeySequence, QShortcut
from app.ui.widgets.preview_workspace import bytes_to_pixmap
from app.ui.widgets.pulse_timeline import PulsePanel
from app.utils.logging_setup import get_logger, set_debug
from app.utils.paths import data_dir, models_dir
from app.utils.performance import ProcessMonitor
from app.vision.pipeline import VisionPipeline

log = get_logger("ui.main_window")

_FRAME_POLL_MS = 33    # ~30 Hz UI refresh
_STATS_POLL_MS = 1000  # 1 Hz CPU/RAM sampling
_HUD_POLL_MS = 500     # 2 Hz HUD + cache refresh

#: Minimum interval between automatic scene summaries (seconds).
_AUTO_SUMMARY_MIN_INTERVAL = 8.0

#: Accepted upload extensions.
_UPLOAD_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"

#: Hard upload size limit (guards against huge files decoding into
#: gigabytes of RAM — 50 MB covers any reasonable photo).
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

#: Onboarding step keys (first-run experience).
_ONBOARDING_STEPS = (
    "check", "models", "camera", "ai", "image", "demo",
)


class _MainBridge(QObject):
    """Worker-thread -> GUI-thread bridge for job/analysis statuses."""

    job_status = Signal(object)          # GenerationJob
    analysis_result = Signal(object)     # (ImageAnalysisResult, ImageRecord|None)
    welcome_check = Signal(str)          # first-run system check summary
    model_download = Signal(str)         # model download completion message
    provider_statuses = Signal(object)   # (llm_status, image_status)
    listen_result = Signal(object)       # Optional[str] STT transcript


class MainWindow(QMainWindow):
    """Top-level window wiring controller, panels and timers."""

    def __init__(
        self,
        settings_service: SettingsService,
        pipeline: Optional[VisionPipeline] = None,
        camera_manager=None,
        parent=None,
        camera_capture_factory=None,
        demo_mode: bool = False,
        defer_vision_load: bool = False,
    ) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._settings = settings_service.settings
        self._monitor = ProcessMonitor()
        self._closing = False
        self._demo_mode = demo_mode
        self._provider_probe_pending = False
        self._last_llm_status: Optional[dict] = None
        self._last_image_status: Optional[dict] = None
        self._defer_vision_load = defer_vision_load

        self.setWindowTitle("AI Vision Lab — Live AI Vision Studio")
        self.resize(1560, 900)
        self.setMinimumSize(1200, 720)

        # Core bridge (camera + pipeline + fps)
        self.controller = CameraController(
            settings_service=settings_service,
            pipeline=pipeline,
            camera_manager=camera_manager,
            parent=self,
            capture_factory=camera_capture_factory,
        )

        # AI + image generation layers.
        self.ai_engine = AIVisionEngine(settings_service)
        self.image_store = ImageStore(data_dir() / "generated")
        self.uploads_store = ImageStore(data_dir() / "uploads")
        self.image_engine = ImageGenerationEngine(
            settings_service, store=self.image_store
        )
        # Local image analysis (lazy-loaded, own pipeline instance).
        self.analysis_engine = ImageAnalysisEngine(models_dir())
        self._last_auto_summary = 0.0

        # Phase 6 state.
        self._selected_record: Optional[ImageRecord] = None
        self._selected_store: Optional[ImageStore] = None
        self._face_reference_path = data_dir() / "face_reference" / "face_ref.png"
        self._analyzed_jobs: set[int] = set()  # auto-analyze guard
        self._captured_snapshot = None          # frozen scene (CAPTURE SCENE)
        self._selected_object: Optional[tuple] = None  # (name, conf, id)
        self._last_generated_file = ""         # latest completed job record
        self._last_result_info = ""            # preview info of that result
        self.reaction_engine = ReactionEngine(report=self._reaction_report)
        # Voice (Phase 17): capability-gated system TTS — status is
        # real | mock | unavailable, reported honestly.
        from app.ai.voice import VoiceEngine

        self.voice_engine = VoiceEngine()
        # Session memory (Phase 22): bounded, RAM-only, privacy-gated.
        from app.ai.memory import SessionMemory

        self.session_memory = SessionMemory()
        # Local extensions (Phase 28): opt-in, isolated, never remote.
        from app.extensions.registry import ExtensionRegistry
        from app.utils.paths import extensions_dir

        self.extension_registry = ExtensionRegistry()
        self.extension_registry.load(
            extensions_dir(),
            enabled=bool(self._settings.extensions_enabled),
        )

        # Gesture actions (Phase 26): cooldown timestamps (monotonic).
        self._gesture_last_open_palm = 0.0
        self._gesture_last_fist = 0.0
        # Cached per-second values (kept out of the 30 Hz frame poll).
        self._cached_delegate: dict[str, str] = {}
        self._cached_generation_status = "idle"
        self._discovered_cameras: list[CameraInfo] = []
        self._last_diagnostics_summary = ""    # last system-check result

        self._main_bridge = _MainBridge()
        self._main_bridge.job_status.connect(self._on_job_status_gui)
        self._main_bridge.analysis_result.connect(self._on_analysis_result_gui)
        self._main_bridge.welcome_check.connect(self._on_welcome_check_gui)
        self._main_bridge.listen_result.connect(self._on_listen_result_gui)
        self._main_bridge.model_download.connect(
            lambda text: self._on_models_downloaded(text)
        )
        self._main_bridge.provider_statuses.connect(
            self._on_provider_statuses_gui
        )
        self.image_engine.on_status(self._main_bridge.job_status.emit)

        self._build_ui()
        self._wire_signals()
        self._apply_initial_settings()

        # Timers: frame pull + system stats (kept cheap).
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_POLL_MS)
        self._frame_timer.timeout.connect(self._poll_frame)
        self._frame_timer.start()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(_STATS_POLL_MS)
        self._stats_timer.timeout.connect(self._poll_stats)
        self._stats_timer.start()

        # Camera discovery in the background; model loading in the foreground
        # (models load in < 1 s once downloaded; first run may download them).
        # With defer_vision_load the window paints first and modules load
        # right after (startup UX: visible state instead of a blank window).
        self.controller.refresh_cameras_async()
        if self._defer_vision_load:
            self.video_widget.set_placeholder(
                "INITIALIZING VISION MODULES …"
            )
        else:
            self._load_vision_modules()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 0, 12, 8)
        root.setSpacing(6)

        self.header = HeaderBar()
        root.addWidget(self.header)

        # --------------------------------------------------------------
        # Body: left navigation rail + stacked pages.
        # --------------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(10)

        self._page_keys: list[str] = []
        self._build_nav_rail()
        body.addWidget(self._nav_rail)

        self._pages = QStackedWidget()
        self._build_home_page()
        self._build_vision_page()
        self._build_create_page()
        self._build_analyze_page()
        self._build_gallery_page()
        self._build_system_page()
        self._build_assistant_page()
        self._build_insights_page()
        body.addWidget(self._pages, 1)
        root.addLayout(body, 1)

        # --------------------------------------------------------------
        # BOTTOM: metrics + activity.
        # --------------------------------------------------------------
        self.status_panel = StatusPanel()
        root.addWidget(self.status_panel)
        self.activity_bar = ActivityBar()
        root.addWidget(self.activity_bar)

        self.setCentralWidget(central)

        # Overlays (toasts bottom-right, command center center).
        self.toasts = ToastManager(central)
        self.command_center = CommandCenter(central)
        self._build_command_center_actions()
        self._update_capture_buttons()

        # Keyboard navigation: Ctrl+1..7 switch pages, Ctrl+K palette.
        for index, key in enumerate(("home", "vision", "create", "analyze",
                                     "gallery", "system", "assistant",
                                     "insights")):
            QShortcut(
                QKeySequence(f"Ctrl+{index + 1}"), self,
                activated=lambda k=key: self._goto_page(k),
            )
        self._page_effects: dict[int, QGraphicsOpacityEffect] = {}
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_stage)
        self._goto_page("home")
        # Window-state memory (Phase 25): size/position/last page.
        self._restore_window_state()

    # ------------------------------------------------------------------
    # Navigation rail + pages
    # ------------------------------------------------------------------
    def _build_nav_rail(self) -> None:
        from PySide6.QtWidgets import QStyle

        self._nav_rail = QFrame()
        self._nav_rail.setObjectName("navRail")
        self._nav_rail.setFixedWidth(178)
        layout = QVBoxLayout(self._nav_rail)
        layout.setContentsMargins(6, 14, 6, 10)
        layout.setSpacing(4)

        brand = QLabel("STUDIO")
        brand.setObjectName("panel_title")
        brand.setContentsMargins(10, 0, 0, 6)
        layout.addWidget(brand)

        self._nav_buttons: dict[str, NavButton] = {}
        nav_items = (
            ("home", "Home", QStyle.StandardPixmap.SP_DesktopIcon, "Ctrl+1"),
            ("vision", "Vision", QStyle.StandardPixmap.SP_MediaPlay, "Ctrl+2"),
            ("create", "Create", QStyle.StandardPixmap.SP_FileDialogNewFolder, "Ctrl+3"),
            ("analyze", "Analyze", QStyle.StandardPixmap.SP_MessageBoxInformation, "Ctrl+4"),
            ("gallery", "Gallery", QStyle.StandardPixmap.SP_DirIcon, "Ctrl+5"),
            ("system", "System", QStyle.StandardPixmap.SP_DriveHDIcon, "Ctrl+6"),
            ("assistant", "Assistant", QStyle.StandardPixmap.SP_MessageBoxQuestion, "Ctrl+7"),
            ("insights", "Insights", QStyle.StandardPixmap.SP_FileDialogDetailedView, "Ctrl+8"),
        )
        for key, label, pixmap_id, shortcut in nav_items:
            button = NavButton(key, label, "")
            icon = self.style().standardIcon(pixmap_id)
            if not icon.isNull():
                button.setIcon(icon)
                button.setIconSize(QSize(16, 16))
            button.setToolTip(f"{label} ({shortcut})")
            button.setAccessibleName(f"Navigate to {label}")
            button.clicked.connect(
                lambda _checked=False, k=key: self._goto_page(k)
            )
            self._nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        self.demo_nav_button = QPushButton("RUN DEMO")
        self.demo_nav_button.setProperty("nav", True)
        self.demo_nav_button.setToolTip(
            "Guided 16-step product tour (simulated camera)."
        )
        self.demo_nav_button.setAccessibleName("Run demo")
        self.demo_nav_button.clicked.connect(self._on_demo_clicked)
        layout.addWidget(self.demo_nav_button)

    def _goto_page(self, key: str) -> None:
        index = self._page_keys.index(key) if key in self._page_keys else 0
        self._pages.setCurrentIndex(index)
        button = self._nav_buttons.get(key)
        if button is not None:
            button.setChecked(True)
        # Subtle page fade-in (GUI thread only, 150 ms, non-blocking).
        page = self._pages.widget(index)
        if page is not None:
            effect = self._page_effects.get(index)
            if effect is None:
                effect = QGraphicsOpacityEffect(page)
                page.setGraphicsEffect(effect)
                self._page_effects[index] = effect
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(150)
            animation.setStartValue(0.55)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.start()

    def _page_frame(self, title: str, subtitle: str = "") -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        header = QVBoxLayout()
        header.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        header.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("pageSubtitle")
            header.addWidget(sub)
        layout.addLayout(header)
        self._current_page_layout = layout
        return page

    # ==================================================================
    # HOME
    # ==================================================================
    def _build_home_page(self) -> None:
        page = self._page_frame("Home", "Status at a glance — every value is live.")
        layout = self._current_page_layout

        # Wrap the page in a scroll area so 1280x720 stays fully usable.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(10)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._home_layout = inner_layout

        # ---------------- hero strip ---------------- #
        hero = QFrame()
        hero.setObjectName("panel")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(12)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(2)
        hero_title = QLabel("AI VISION LAB")
        hero_title.setObjectName("heroTitle")
        hero_text.addWidget(hero_title)
        hero_sub = QLabel("Live AI vision studio — local-first, honest status.")
        hero_sub.setObjectName("hint")
        hero_text.addWidget(hero_sub)
        hero_layout.addLayout(hero_text, 1)
        hero_state = QVBoxLayout()
        hero_state.setSpacing(4)
        state_caption = QLabel("SYSTEM STATE")
        state_caption.setObjectName("kpi_label")
        hero_state.addWidget(state_caption)
        self._hero_state_badge = StatusBadge()
        hero_state.addWidget(self._hero_state_badge)
        self._hero_state_detail = QLabel("")
        self._hero_state_detail.setObjectName("hint")
        self._hero_state_detail.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        hero_state.addWidget(self._hero_state_detail)
        hero_layout.addLayout(hero_state)
        inner_layout.addWidget(hero)

        # ---------------- first-run onboarding ---------------- #
        self._welcome_card = QFrame()
        self._welcome_card.setObjectName("panel")
        welcome_layout = QVBoxLayout(self._welcome_card)
        welcome_layout.setContentsMargins(18, 14, 18, 14)
        welcome_layout.setSpacing(8)
        welcome_row = QHBoxLayout()
        welcome_title = QLabel("WELCOME TO AI VISION LAB")
        welcome_title.setObjectName("pageTitle")
        welcome_row.addWidget(welcome_title)
        welcome_row.addStretch(1)
        self.welcome_dismiss_button = QPushButton("DISMISS")
        self.welcome_dismiss_button.setObjectName("ghost")
        self.welcome_dismiss_button.clicked.connect(self._dismiss_welcome)
        welcome_row.addWidget(self.welcome_dismiss_button)
        welcome_layout.addLayout(welcome_row)
        welcome_text = QLabel(
            "Six steps to a working studio — most are optional. "
            "Everything here shows real state: nothing is simulated."
        )
        welcome_text.setObjectName("hint")
        welcome_text.setWordWrap(True)
        welcome_layout.addWidget(welcome_text)

        self._onboarding_badges: dict[str, StatusBadge] = {}
        self._onboarding_buttons: dict[str, QPushButton] = {}
        step_rows = QHBoxLayout()
        step_rows.setSpacing(10)
        left_steps = QVBoxLayout()
        right_steps = QVBoxLayout()
        left_steps.setSpacing(6)
        right_steps.setSpacing(6)
        for index, key in enumerate(_ONBOARDING_STEPS):
            row = QHBoxLayout()
            row.setSpacing(8)
            number = QLabel(f"{index + 1:02d}")
            number.setObjectName("value_dim")
            row.addWidget(number)
            name = QLabel({
                "check": "SYSTEM CHECK",
                "models": "VISION MODELS",
                "camera": "CAMERA SETUP",
                "ai": "AI PROVIDER",
                "image": "IMAGE PROVIDER",
                "demo": "START DEMO",
            }[key])
            row.addWidget(name)
            row.addStretch(1)
            badge = StatusBadge()
            badge.set_status("idle", "—")
            self._onboarding_badges[key] = badge
            row.addWidget(badge)
            button = QPushButton("")
            button.setVisible(False)
            button.clicked.connect(
                lambda _checked=False, k=key: self._onboarding_action(k)
            )
            self._onboarding_buttons[key] = button
            row.addWidget(button)
            (left_steps if index < 3 else right_steps).addLayout(row)
        step_rows.addLayout(left_steps, 1)
        step_rows.addLayout(right_steps, 1)
        welcome_layout.addLayout(step_rows)

        self.welcome_check_button = QPushButton("RUN SYSTEM CHECK")
        self.welcome_check_button.setObjectName("primary")
        self.welcome_check_button.clicked.connect(self._run_welcome_check)
        self.welcome_demo_button = QPushButton("TRY THE DEMO")
        self.welcome_demo_button.clicked.connect(self._on_demo_clicked)
        welcome_actions = QHBoxLayout()
        welcome_actions.addWidget(self.welcome_check_button)
        welcome_actions.addWidget(self.welcome_demo_button)
        welcome_actions.addStretch(1)
        welcome_layout.addLayout(welcome_actions)

        self._welcome_check_result = QLabel("")
        self._welcome_check_result.setObjectName("value_dim")
        self._welcome_check_result.setWordWrap(True)
        welcome_layout.addWidget(self._welcome_check_result)
        inner_layout.addWidget(self._welcome_card)
        self._welcome_card.setVisible(not self._settings.first_run_done)

        # ---------------- status cards ---------------- #
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self._home_cards = {}
        for key, title in (("camera", "CAMERA"), ("vision", "VISION"),
                           ("ai", "AI"), ("image", "IMAGE ENGINE"),
                           ("system", "SYSTEM")):
            card = MetricCard(title)
            self._home_cards[key] = card
            cards.addWidget(card)
        inner_layout.addLayout(cards)

        # ---------------- quick actions ---------------- #
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        actions = (
            ("START LIVE", "Start the selected camera and live vision.",
             self._on_start_clicked),
            ("CAPTURE SCENE", "Freeze the current scene snapshot for "
             "generation, copy and save.", self._capture_scene),
            ("GENERATE", "Open the CREATE page (Ctrl+3).",
             lambda: self._goto_page("create")),
            ("ANALYZE", "Open the ANALYZE page (Ctrl+4).",
             lambda: self._goto_page("analyze")),
            ("GALLERY", "Open the asset library (Ctrl+5).",
             lambda: self._goto_page("gallery")),
            ("RUN DEMO", "Guided 16-step product tour (simulated camera).",
             self._on_demo_clicked),
            ("SYSTEM CHECK", "Run the 9-check diagnostics.",
             self._run_welcome_check),
        )
        for label, tooltip, handler in actions:
            button = QPushButton(label)
            if label == "START LIVE":
                button.setObjectName("primary")
            button.setToolTip(tooltip)
            button.setAccessibleName(f"Quick action: {label}")
            button.clicked.connect(handler)
            actions_row.addWidget(button)
        inner_layout.addLayout(actions_row)

        # ---------------- recent activity + results ---------------- #
        middle = QHBoxLayout()
        middle.setSpacing(8)

        activity_card = QFrame()
        activity_card.setObjectName("panel")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(12, 10, 12, 12)
        activity_layout.addWidget(SectionHeader("Recent Activity"))
        self._home_activity = QListWidget()
        self._home_activity.setMaximumHeight(140)
        activity_layout.addWidget(self._home_activity)
        middle.addWidget(activity_card, 1)

        results_card = QFrame()
        results_card.setObjectName("panel")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(12, 10, 12, 12)
        results_layout.addWidget(SectionHeader("Recent Results"))
        self._home_results = QHBoxLayout()
        self._home_results.setSpacing(8)
        results_layout.addLayout(self._home_results)
        self._home_results_empty = EmptyState(
            "NO IMAGES YET",
            "Generate your first image or upload one.",
            action_text="OPEN GALLERY",
        )
        self._home_results_empty.action_button.clicked.connect(
            lambda: self._goto_page("gallery")
        )
        self._home_results_empty.setMaximumHeight(140)
        results_layout.addWidget(self._home_results_empty)
        results_layout.addStretch(1)
        middle.addWidget(results_card, 1)
        inner_layout.addLayout(middle)

        # ---------------- system health ---------------- #
        health_card = QFrame()
        health_card.setObjectName("panel")
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(12, 10, 12, 12)
        health_row = QHBoxLayout()
        health_row.addWidget(SectionHeader("System Health"))
        health_row.addStretch(1)
        self.health_check_button = QPushButton("SYSTEM CHECK")
        self.health_check_button.setObjectName("ghost")
        self.health_check_button.setToolTip(
            "Run the 9-check diagnostics (Python, models, camera, GPU, "
            "providers, storage)."
        )
        self.health_check_button.setAccessibleName("System health check")
        self.health_check_button.clicked.connect(self._run_welcome_check)
        health_row.addWidget(self.health_check_button)
        health_layout.addLayout(health_row)
        health_grid = QHBoxLayout()
        health_grid.setSpacing(16)
        self._health_badges: dict[str, StatusBadge] = {}
        for key in ("camera", "vision", "ai", "gpu", "image"):
            row = QVBoxLayout()
            row.setSpacing(2)
            label = QLabel(key.upper())
            label.setObjectName("kpi_label")
            row.addWidget(label)
            badge = StatusBadge()
            self._health_badges[key] = badge
            row.addWidget(badge)
            health_grid.addLayout(row)
        health_grid.addStretch(1)
        health_layout.addLayout(health_grid)
        inner_layout.addWidget(health_card)
        inner_layout.addStretch(1)

        self._page_keys.append("home")
        self._pages.addWidget(page)

    # ------------------------------------------------------------------
    # Onboarding (first-run experience)
    # ------------------------------------------------------------------
    def _onboarding_action(self, key: str) -> None:
        if key == "check":
            self._run_welcome_check()
        elif key == "models":
            self._download_models_onboarding()
        elif key == "camera":
            self.controller.refresh_cameras_async()
            self.toasts.notify("Rescanning for cameras…", "info")
        elif key == "demo":
            self.start_demo()

    def _refresh_onboarding(self) -> None:
        """Real state for every onboarding step (no simulated values)."""
        if not hasattr(self, "_onboarding_badges"):
            return
        from app.vision.model_manager import MODEL_REGISTRY

        # 1) SYSTEM CHECK
        if self._last_diagnostics_summary:
            self._set_onboarding(
                "check", "ready" if "pass" in self._last_diagnostics_summary
                else "error", self._last_diagnostics_summary[:60],
                button_text="RECHECK",
            )
        else:
            self._set_onboarding("check", "idle", "ACTION REQUIRED",
                                 button_text="RUN")

        # 2) MODELS
        missing = [
            name for name, (filename, _url, minimum) in MODEL_REGISTRY.items()
            if not (models_dir() / filename).is_file()
            or (models_dir() / filename).stat().st_size < minimum
        ]
        if missing:
            self._set_onboarding(
                "models", "error", "ACTION REQUIRED — MISSING",
                button_text="DOWNLOAD",
            )
        else:
            self._set_onboarding("models", "ready", "READY",
                                 button_text="VERIFY")

        # 3) CAMERA
        if self._discovered_cameras:
            self._set_onboarding("camera", "ready",
                                 f"READY — {len(self._discovered_cameras)}",
                                 button_text="RESCAN")
        else:
            self._set_onboarding("camera", "untestable", "UNAVAILABLE",
                                 button_text="RESCAN")

        # 4/5) Providers — cached only. This method runs from the 2 Hz
        # home refresh on the GUI thread; a force-probe here would freeze
        # the UI for the HTTP timeout whenever Ollama/SD WebUI is down.
        llm = (
            self.ai_engine.provider_status_cached()
            or self._last_llm_status
            or {"status": "checking", "detail": "…"}
        )
        if llm["status"] == "online":
            self._set_onboarding("ai", "ready", "READY — ONLINE")
        elif llm["status"] == "mock":
            self._set_onboarding("ai", "mock", "OPTIONAL — MOCK")
        elif llm["status"] == "checking":
            self._set_onboarding("ai", "idle", "CHECKING…")
        else:
            self._set_onboarding("ai", "idle", "OPTIONAL — OFFLINE")

        image = (
            self.image_engine.provider_status_cached()
            or self._last_image_status
            or {"status": "checking", "detail": "…"}
        )
        if image["status"] == "online":
            self._set_onboarding("image", "ready", "READY — ONLINE")
        elif image["status"] == "mock":
            self._set_onboarding("image", "mock", "OPTIONAL — MOCK")
        elif image["status"] == "unavailable":
            self._set_onboarding("image", "idle", "OPTIONAL — NONE")
        elif image["status"] == "checking":
            self._set_onboarding("image", "idle", "CHECKING…")
        else:
            self._set_onboarding("image", "ready", "READY — CONFIGURED")

        # 6) DEMO
        self._set_onboarding("demo", "ready", "READY", button_text="START")

    def _set_onboarding(self, key: str, status: str, text: str,
                        button_text: str = "") -> None:
        badge = self._onboarding_badges.get(key)
        button = self._onboarding_buttons.get(key)
        if badge is not None:
            badge.set_status(status, text)
        if button is not None:
            if button_text:
                button.setText(button_text)
                button.setVisible(True)
            else:
                button.setVisible(False)

    def _download_models_onboarding(self) -> None:
        from app.vision.model_manager import ModelManager

        manager = ModelManager(models_dir())
        self._set_onboarding("models", "processing", "DOWNLOADING…")

        def _work() -> None:
            try:
                manager.download_all()
                if not self._closing:
                    self._main_bridge.model_download.emit("downloaded")
            except Exception as exc:  # noqa: BLE001 — readable UI message
                log.warning("Model download failed: %s", exc)
                if not self._closing:
                    self._main_bridge.model_download.emit(f"failed: {exc}")

        threading.Thread(
            target=_work, name="model-download", daemon=True
        ).start()

    def _on_models_downloaded(self, message: str) -> None:
        if message == "downloaded":
            self.toasts.notify("Vision models ready.", "success")
        else:
            self.toasts.notify_error(
                "Model download failed.",
                why=message.replace("failed: ", "", 1)[:100],
                fix="Run: python scripts/download_models.py (needs internet).",
                details=message,
            )
        self._refresh_onboarding()

    # ==================================================================
    # VISION
    # ==================================================================
    def _build_vision_page(self) -> None:
        page = self._page_frame(
            "Vision", "Live camera analysis — the visual center of the studio."
        )
        layout = self._current_page_layout

        body = QHBoxLayout()
        body.setSpacing(10)

        # ---------------- LEFT: controls ---------------- #
        left = QWidget()
        left.setFixedWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.camera_panel = CameraPanel()
        left_layout.addWidget(self.camera_panel)

        self.vision_controls = VisionControlsPanel(self._settings_service)
        self.vision_controls.mode_changed.connect(
            lambda mode: self.controller.update_settings(vision_mode=mode)
        )
        left_layout.addWidget(self.vision_controls)

        self._details_toggle = QPushButton("ADVANCED ▸")
        self._details_toggle.setObjectName("collapseToggle")
        self._details_toggle.clicked.connect(self._toggle_details)
        left_layout.addWidget(self._details_toggle)

        # Stage Mode (Phase 25): clean frameless live feed for a second
        # monitor or screen sharing.
        self.stage_button = QPushButton("STAGE MODE")
        self.stage_button.setObjectName("ghost")
        self.stage_button.setToolTip(
            "Open a clean, frameless live-feed window for a second "
            "monitor or screen sharing (F11)."
        )
        self.stage_button.setAccessibleName("Toggle stage mode")
        self.stage_button.clicked.connect(self._toggle_stage)
        left_layout.addWidget(self.stage_button)

        capture_row = QHBoxLayout()
        self.record_button = QPushButton("RECORD")
        self.record_button.setObjectName("danger")
        self.record_button.setToolTip(
            "Record the live camera locally (never uploaded). "
            "Stops automatically after 10 minutes or 2 GB."
        )
        self.record_button.setAccessibleName("Start or stop recording")
        self.record_button.clicked.connect(self._toggle_recording)
        capture_row.addWidget(self.record_button)
        self.snapshot_button = QPushButton("SNAPSHOT")
        self.snapshot_button.setObjectName("ghost")
        self.snapshot_button.setToolTip(
            "Save the current camera frame as a JPEG in data/recordings."
        )
        self.snapshot_button.setAccessibleName("Take snapshot")
        self.snapshot_button.clicked.connect(self._take_snapshot)
        capture_row.addWidget(self.snapshot_button)
        left_layout.addLayout(capture_row)
        self._record_status = QLabel("")
        self._record_status.setObjectName("hint")
        left_layout.addWidget(self._record_status)

        self._details_widget = QWidget()
        details_layout = QVBoxLayout(self._details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(6)
        self.analysis_panel = AnalysisPanel()
        self.gaze_panel = GazePanel()
        self.vision_panel = VisionPanel()
        self.modules_panel = ModulesPanel(self._settings_service)
        details_layout.addWidget(self.analysis_panel)
        details_layout.addWidget(self.gaze_panel)
        details_layout.addWidget(self.vision_panel)
        details_layout.addWidget(self.modules_panel)
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        details_scroll.setWidget(self._details_widget)
        self._details_widget.setVisible(False)
        left_layout.addWidget(details_scroll, 1)
        body.addWidget(left)

        # ---------------- CENTER: live feed ---------------- #
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        video_frame = QFrame()
        video_frame.setObjectName("panel")
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(8, 8, 8, 8)
        self.video_widget = VideoWidget()
        video_layout.addWidget(self.video_widget)
        center_layout.addWidget(video_frame, 1)

        # Minimalist HUD over the feed (real values only, 2 Hz).
        self.hud = HudOverlay(self.video_widget)
        self.hud.set_visible(True)

        self.live_state_panel = LiveStatePanel()
        center_layout.addWidget(self.live_state_panel)

        # Scene pulse (Phase 26): real event timeline under the feed.
        self.pulse_panel = PulsePanel()
        self.pulse_panel.timeline.set_window_seconds(300)
        center_layout.addWidget(self.pulse_panel)
        body.addWidget(center, 1)

        # ---------------- RIGHT: scene + object + inspector ---------------- #
        right = QWidget()
        right.setFixedWidth(340)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        scene_panel = QFrame()
        scene_panel.setObjectName("panel")
        scene_layout = QVBoxLayout(scene_panel)
        scene_layout.setContentsMargins(12, 10, 12, 10)
        scene_layout.setSpacing(6)
        scene_layout.addWidget(SectionHeader("SCENE"))
        scene_row = QHBoxLayout()
        self.capture_scene_button = QPushButton("CAPTURE SCENE")
        self.capture_scene_button.setObjectName("primary")
        self.capture_scene_button.setToolTip(
            "Freeze the current scene (objects, persons, pose) for the "
            "generate/copy/save actions below."
        )
        self.capture_scene_button.setAccessibleName("Capture scene")
        self.capture_scene_button.clicked.connect(self._capture_scene)
        scene_row.addWidget(self.capture_scene_button)
        self.generate_scene_button = QPushButton("GENERATE FROM SCENE")
        self.generate_scene_button.setToolTip(
            "Build a prompt from the captured scene and queue a generation."
        )
        self.generate_scene_button.setAccessibleName("Generate from scene")
        self.generate_scene_button.clicked.connect(self._generate_from_scene)
        scene_row.addWidget(self.generate_scene_button)
        scene_layout.addLayout(scene_row)
        scene_row2 = QHBoxLayout()
        self.copy_scene_button = QPushButton("COPY SCENE")
        self.copy_scene_button.setToolTip(
            "Copy the structured scene description to the clipboard."
        )
        self.copy_scene_button.setAccessibleName("Copy scene")
        self.copy_scene_button.clicked.connect(self._copy_scene)
        scene_row2.addWidget(self.copy_scene_button)
        self.save_snapshot_button = QPushButton("SAVE SNAPSHOT")
        self.save_snapshot_button.setToolTip(
            "Save the captured scene as JSON (data/snapshots, no images)."
        )
        self.save_snapshot_button.setAccessibleName("Save snapshot")
        self.save_snapshot_button.clicked.connect(self._save_snapshot)
        scene_row2.addWidget(self.save_snapshot_button)
        scene_layout.addLayout(scene_row2)
        self._capture_buttons = [
            self.generate_scene_button, self.copy_scene_button,
            self.save_snapshot_button,
        ]
        right_layout.addWidget(scene_panel)

        object_panel = QFrame()
        object_panel.setObjectName("panel")
        object_layout = QVBoxLayout(object_panel)
        object_layout.setContentsMargins(12, 10, 12, 10)
        object_layout.setSpacing(6)
        object_layout.addWidget(SectionHeader("SELECTED OBJECT"))
        self._object_selection_label = QLabel("none — pick an object in "
                                              "VISION ANALYSIS")
        self._object_selection_label.setObjectName("value_dim")
        self._object_selection_label.setWordWrap(True)
        object_layout.addWidget(self._object_selection_label)
        object_row = QHBoxLayout()
        self.generate_object_button = QPushButton("GENERATE OBJECT")
        self.generate_object_button.clicked.connect(self._generate_object)
        object_row.addWidget(self.generate_object_button)
        self.copy_object_button = QPushButton("COPY NAME")
        self.copy_object_button.clicked.connect(self._copy_object_name)
        object_row.addWidget(self.copy_object_button)
        object_layout.addLayout(object_row)
        right_layout.addWidget(object_panel)

        self.inspector_panel = InspectorPanel()
        right_layout.addWidget(self.inspector_panel, 1)
        body.addWidget(right)
        layout.addLayout(body)

        self._page_keys.append("vision")
        self._pages.addWidget(page)

    def _toggle_details(self) -> None:
        visible = self._details_widget.isVisible()
        self._details_widget.setVisible(not visible)
        self._details_toggle.setText(
            "ADVANCED ▾" if not visible else "ADVANCED ▸"
        )

    # ==================================================================
    # CREATE
    # ==================================================================
    def _build_create_page(self) -> None:
        page = self._page_frame(
            "Create", "Text-to-image from your prompt — or from the live scene."
        )
        layout = self._current_page_layout

        body = QHBoxLayout()
        body.setSpacing(10)

        # ---------------- LEFT: prompt + settings ---------------- #
        self.image_panel = ImagePanel(
            self.image_engine,
            snapshot_provider=self._current_snapshot,
            settings_service=self._settings_service,
        )
        self.image_panel.setMaximumWidth(420)
        self.image_panel.setMinimumWidth(360)
        body.addWidget(self.image_panel)

        # ---------------- CENTER: large preview ---------------- #
        from app.ui.widgets.preview_workspace import _PreviewLabel

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        preview_frame = QFrame()
        preview_frame.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        self._create_preview = _PreviewLabel(
            "NO RESULT YET\nGenerate your first image."
        )
        preview_layout.addWidget(self._create_preview)
        center_layout.addWidget(preview_frame, 1)

        self._create_info = QLabel("")
        self._create_info.setObjectName("value_dim")
        self._create_info.setWordWrap(True)
        center_layout.addWidget(self._create_info)
        body.addWidget(center, 1)

        # ---------------- RIGHT: result information ---------------- #
        right = QFrame()
        right.setObjectName("panel")
        right.setFixedWidth(260)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 12)
        right_layout.setSpacing(8)
        right_layout.addWidget(SectionHeader("RESULT"))
        self._create_result_info = QLabel("No result yet.")
        self._create_result_info.setObjectName("value_dim")
        self._create_result_info.setWordWrap(True)
        right_layout.addWidget(self._create_result_info)
        self._create_result_status = StatusBadge()
        self._create_result_status.set_status("idle", "IDLE")
        right_layout.addWidget(self._create_result_status)
        self._create_processing = QLabel("")
        self._create_processing.setObjectName("hint")
        self._create_processing.setWordWrap(True)
        right_layout.addWidget(self._create_processing)
        right_layout.addStretch(1)
        actions_title = SectionHeader("ACTIONS")
        right_layout.addWidget(actions_title)
        self._create_analyze = QPushButton("ANALYZE")
        self._create_analyze.setToolTip(
            "Analyze the latest result locally and open ANALYZE."
        )
        self._create_analyze.clicked.connect(self._create_action_analyze)
        right_layout.addWidget(self._create_analyze)
        self._create_regenerate = QPushButton("REGENERATE")
        self._create_regenerate.setToolTip(
            "Queue a new version of the latest result (v2, v3, …)."
        )
        self._create_regenerate.clicked.connect(self._create_action_regenerate)
        right_layout.addWidget(self._create_regenerate)
        self._create_vary = QPushButton("VARY")
        self._create_vary.setToolTip(
            "Image-to-image variation of the latest result "
            "(providers that support img2img only)."
        )
        self._create_vary.clicked.connect(self._vary_selected)
        right_layout.addWidget(self._create_vary)
        self._create_compare = QPushButton("COMPARE")
        self._create_compare.setToolTip(
            "Compare the latest result with its previous version."
        )
        self._create_compare.clicked.connect(self._create_action_compare)
        right_layout.addWidget(self._create_compare)
        self._create_save = QPushButton("SAVE COPY")
        self._create_save.setObjectName("primary")
        self._create_save.setToolTip("Save the latest result to a file.")
        self._create_save.clicked.connect(self._create_action_save)
        right_layout.addWidget(self._create_save)
        body.addWidget(right)
        layout.addLayout(body)

        self._page_keys.append("create")
        self._pages.addWidget(page)
        self._update_create_actions()

    def _update_create_actions(self) -> None:
        """Workflow gating: RESULT actions only when a result exists.

        Uses the last-completed file marker (set on every completion)
        plus the store — never the queue, which prunes old terminal
        jobs. No action is offered that cannot work right now.
        """
        has_result = bool(self._last_generated_file) or bool(
            self.image_store.list(limit=1)
        )
        for button in (
            self._create_analyze, self._create_regenerate,
            self._create_vary, self._create_compare, self._create_save,
        ):
            button.setEnabled(has_result)
            if not has_result and not button.toolTip():
                button.setToolTip(
                    "Generate an image first — this action needs a result."
                )

    def _create_action_save(self) -> None:
        record = self._latest_completed_record()
        if record is None:
            self.toasts.notify(
                "Nothing to save yet — generate an image first.", "warning"
            )
            return
        store = self._store_for(record)
        if store is None:
            return
        try:
            png_bytes = store.path_of(record).read_bytes()
        except OSError:
            self.toasts.notify_error(
                "Could not read the image file.",
                why="The stored image is missing or unreadable.",
                fix="Regenerate the image and try again.",
            )
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save image as", f"{record.file}", _UPLOAD_FILTER
        )
        if not path:
            return
        try:
            with open(path, "wb") as handle:
                handle.write(png_bytes)
        except OSError as exc:
            self.toasts.notify_error(
                "Could not save the image.",
                why=str(exc),
                fix="Choose a writable folder and try again.",
                details=str(exc),
            )
            return
        self.toasts.notify("Image saved.", "success")

    # ==================================================================
    # ANALYZE / GALLERY / SYSTEM / ASSISTANT
    # ==================================================================
    def _build_analyze_page(self) -> None:
        page = self._page_frame(
            "Analyze", "Upload, analyze and compare — local vision analysis."
        )
        layout = self._current_page_layout

        center_frame = QFrame()
        center_frame.setObjectName("panel")
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(8, 8, 8, 8)
        self.preview_workspace = PreviewWorkspace()
        center_layout.addWidget(self.preview_workspace)
        layout.addWidget(center_frame, 1)

        self.analysis_tab_panel = ImageAnalysisPanel()
        layout.addWidget(self.analysis_tab_panel)

        self._page_keys.append("analyze")
        self._pages.addWidget(page)

    def _build_gallery_page(self) -> None:
        page = self._page_frame(
            "Gallery", "Asset library — generated and uploaded images."
        )
        layout = self._current_page_layout

        self.gallery_panel = GalleryPanel(
            self.image_engine,
            generated_store=self.image_store,
            uploads_store=self.uploads_store,
        )
        self.gallery_panel.set_empty_action(
            lambda: self._goto_page("create")
        )
        layout.addWidget(self.gallery_panel, 1)

        self._page_keys.append("gallery")
        self._pages.addWidget(page)

    def _build_system_page(self) -> None:
        page = self._page_frame(
            "System", "Providers, capabilities, diagnostics and privacy."
        )
        layout = self._current_page_layout

        self.system_panel = SystemPanel(
            self._settings_service, self.ai_engine, self.image_engine,
            diagnostics_callback=self._run_system_check_worker,
        )
        layout.addWidget(self.system_panel, 1)

        self._page_keys.append("system")
        self._pages.addWidget(page)

    def _build_assistant_page(self) -> None:
        page = self._page_frame(
            "Assistant",
            "Ask about the live scene — deterministic commands work offline.",
        )
        layout = self._current_page_layout

        self.ai_panel = AIPanel(
            self.ai_engine, snapshot_provider=self._current_snapshot
        )
        self.ai_panel.set_image_intent_handler(self._handle_image_intent)
        self.ai_panel.set_vision_intent_handler(self._handle_vision_intent)
        self.ai_panel.set_watch_handler(self._handle_watch_request)
        layout.addWidget(self.ai_panel, 1)

        self._page_keys.append("assistant")
        self._pages.addWidget(page)

    def _build_insights_page(self) -> None:
        page = self._page_frame(
            "Insights",
            "Session analytics — real data only, never stored.",
        )
        layout = self._current_page_layout
        self.insights_panel = InsightsPanel()
        layout.addWidget(self.insights_panel, 1)
        self._page_keys.append("insights")
        self._pages.addWidget(page)

    # ------------------------------------------------------------------
    # Command center + demo entry
    # ------------------------------------------------------------------
    def _build_command_center_actions(self) -> None:
        entries = [
            ("NAVIGATION", "goto_home", "Go to Home", "Ctrl+1",
             lambda: self._goto_page("home")),
            ("NAVIGATION", "goto_vision", "Go to Vision", "Ctrl+2",
             lambda: self._goto_page("vision")),
            ("NAVIGATION", "goto_create", "Go to Create", "Ctrl+3",
             lambda: self._goto_page("create")),
            ("NAVIGATION", "goto_analyze", "Go to Analyze", "Ctrl+4",
             lambda: self._goto_page("analyze")),
            ("NAVIGATION", "goto_gallery", "Go to Gallery", "Ctrl+5",
             lambda: self._goto_page("gallery")),
            ("NAVIGATION", "goto_system", "Go to System", "Ctrl+6",
             lambda: self._goto_page("system")),
            ("NAVIGATION", "goto_assistant", "Go to Assistant", "Ctrl+7",
             lambda: self._goto_page("assistant")),
            ("NAVIGATION", "goto_insights", "Go to Insights", "Ctrl+8",
             lambda: self._goto_page("insights")),
            ("VISION", "start_camera", "Start Camera", "",
             self._on_start_clicked),
            ("VISION", "stop_camera", "Stop Camera", "",
             self._on_stop_clicked),
            ("VISION", "capture_scene", "Capture Scene", "",
             self._capture_scene),
            ("VISION", "stage_mode", "Toggle Stage Mode", "F11",
             self._toggle_stage),
            ("VISION", "toggle_record", "Start / Stop Recording", "",
             self._toggle_recording),
            ("VISION", "take_snapshot", "Take Snapshot", "",
             self._take_snapshot),
            ("IMAGE", "generate_image", "Generate Image", "",
             lambda: self._goto_page("create")),
            ("IMAGE", "analyze_image", "Analyze Image", "",
             lambda: self._goto_page("analyze")),
            ("IMAGE", "open_gallery", "Open Gallery", "",
             lambda: self._goto_page("gallery")),
            ("AI", "open_assistant", "AI Assistant", "",
             lambda: self._goto_page("assistant")),
            ("AI", "clear_chat", "Clear Chat", "Ctrl+L",
             lambda: self.ai_panel._on_clear()),
            ("SYSTEM", "run_demo", "Run Demo", "",
             self._on_demo_clicked),
            ("SYSTEM", "system_check", "Run System Check", "",
             self._run_welcome_check),
            ("SYSTEM", "refresh_providers", "Refresh Provider Status", "",
             self._refresh_provider_status),
            ("SYSTEM", "toggle_theme", "Toggle Theme", "",
             self._toggle_theme_action),
        ]
        self.command_center.set_actions_v2(entries)

    def _toggle_theme_action(self) -> None:
        new_dark = not bool(self._settings.dark_theme)
        self._settings_service.update(dark_theme=new_dark)
        apply_theme(QApplication.instance(), new_dark)
        self._apply_theme_visuals()

    def _apply_theme_visuals(self) -> None:
        """Push the active palette into every widget with programmatic
        colors (video placeholder, previews, chat, reports, HUD, …).

        Both themes are fully usable: dark = premium command center,
        light = clean professional.
        """
        for target in (
            self.video_widget,
            self.hud,
        ):
            target.apply_palette() if hasattr(target, "apply_palette") else None
        self.live_state_panel.apply_palette()
        self.inspector_panel.apply_palette()
        self.gallery_panel.apply_palette()
        self.ai_panel.apply_palette()
        self.analysis_tab_panel.apply_palette()
        for label in (self.preview_workspace.result_label,
                      self.preview_workspace.upload_label,
                      self.preview_workspace.compare_view.left_label,
                      self.preview_workspace.compare_view.right_label,
                      self._create_preview):
            if hasattr(label, "apply_palette"):
                label.apply_palette()

    def _on_demo_clicked(self) -> None:
        self.start_demo()

    def _on_welcome_check_gui(self, text: str) -> None:
        """GUI thread: render the system-check summary (never from a worker)."""
        self._welcome_check_result.setText(text)
        self._refresh_onboarding()

    def _run_welcome_check(self) -> None:
        """First-run system check: runs in a worker, shows the summary."""
        self._welcome_check_result.setText("Running system check…")
        self._set_onboarding("check", "processing", "RUNNING…")

        def _done(report) -> None:
            counts = (
                f"{sum(1 for c in report.checks if c.status == 'PASS')} pass · "
                f"{sum(1 for c in report.checks if c.status == 'FAIL')} fail · "
                f"{sum(1 for c in report.checks if c.status == 'UNAVAILABLE')} "
                "unavailable"
            )
            details = " · ".join(
                f"{c.name}: {c.status}" for c in report.checks
            )
            self._last_diagnostics_summary = counts
            if self._closing:
                return
            try:
                self._main_bridge.welcome_check.emit(f"{counts}\n{details}")
            except RuntimeError:
                return  # window teardown — receivers already gone

        self._run_system_check_worker(_done)

    def _run_system_check_worker(self, on_done) -> None:
        """Run diagnostics in a worker; pass the report back on the GUI
        thread. Used by the home onboarding and the SYSTEM page."""

        def _work() -> None:
            from app.diagnostics import run_diagnostics

            report = run_diagnostics()
            on_done(report)

        threading.Thread(
            target=_work, name="system-check", daemon=True
        ).start()

    def _dismiss_welcome(self) -> None:
        self._settings_service.update(first_run_done=True)
        self._welcome_card.setVisible(False)
        self.toasts.notify(
            "Welcome dismissed — see SYSTEM for details.", "info"
        )

    # ------------------------------------------------------------------
    # Create page result actions
    # ------------------------------------------------------------------
    def _latest_completed_record(self) -> Optional[ImageRecord]:
        """The most recent completed generation — from the queue, with a
        store fallback (the queue prunes terminal jobs beyond 60, so the
        store is the source of truth for long sessions)."""
        jobs = [
            j for j in self.image_engine.queue.active_jobs()
            if j.status == "COMPLETED" and j.record is not None
        ]
        if jobs:
            jobs.sort(key=lambda j: j.id)
            record = jobs[-1].record
            self._select_record(record, self.image_store)
            return record
        records = self.image_store.list(limit=1)
        if not records:
            return None
        record = records[0]
        self._select_record(record, self.image_store)
        return record

    def _create_action_analyze(self) -> None:
        record = self._latest_completed_record()
        if record is None:
            self.toasts.notify(
                "Nothing to analyze yet — generate an image first.", "warning"
            )
            return
        self._gallery_analyze(record)
        self._goto_page("analyze")

    def _create_action_regenerate(self) -> None:
        record = self._latest_completed_record()
        if record is None:
            self.toasts.notify(
                "Nothing to regenerate yet — generate an image first.", "warning"
            )
            return
        if record.feedback:
            self._regenerate_with_feedback()
        else:
            self._gallery_regenerate(record)
        self.toasts.notify("Regeneration queued.", "info")

    def _create_action_compare(self) -> None:
        record = self._latest_completed_record()
        if record is None:
            self.toasts.notify(
                "Nothing to compare yet — generate an image first.", "warning"
            )
            return
        self._compare_selected()
        self._goto_page("analyze")

    # ------------------------------------------------------------------
    # Home page refresh
    # ------------------------------------------------------------------
    def _refresh_home(self) -> None:
        if not hasattr(self, "_home_cards"):
            return
        running = self.controller.is_running
        self._home_cards["camera"].set_value(
            "● LIVE" if running else "○ STANDBY",
            "live" if running else "idle",
        )
        _frame, result, _stats = self.controller.latest()
        if result is not None:
            self._home_cards["vision"].set_value(
                f"{len(result.objects)} obj · {len(result.persons)} person",
            )
        # Non-blocking provider statuses (cache + background probe).
        llm = self.ai_engine.provider_status_cached() or self._last_llm_status
        if llm is None:
            llm = {"status": "checking", "detail": "…"}
        image_status = (
            self.image_engine.provider_status_cached()
            or self._last_image_status
        )
        if image_status is None:
            image_status = {"status": "checking", "detail": "…"}
        self._home_cards["ai"].set_value(llm["status"].upper(), llm["status"])
        self._home_cards["image"].set_value(
            image_status["status"].upper(), image_status["status"]
        )
        self._home_cards["system"].set_value(
            self._last_diagnostics_summary or "NOT CHECKED",
            "ready" if "pass" in (self._last_diagnostics_summary or "")
            else "idle",
        )

        # Header provider cluster + hero state (real values only).
        self.header.set_delegate(self._cached_delegate)
        self.header.set_llm_status(llm["status"])
        self.header.set_image_status(image_status["status"])
        self._refresh_hero_state(llm, image_status)

        delegate = self.controller.delegate_summary()
        gpu_active = any("gpu" in m for m in delegate.values())
        for key in ("camera", "vision", "ai", "gpu", "image"):
            badge = self._health_badges.get(key)
            if badge is None:
                continue
            if key == "camera":
                badge.set_status(
                    "live" if running else "idle",
                    "LIVE" if running else "STANDBY",
                )
            elif key in ("vision", "gpu"):
                badge.set_status(
                    "gpu" if gpu_active else "cpu",
                    "GPU" if gpu_active else "CPU",
                )
            elif key == "ai":
                badge.set_status(llm["status"], llm["status"])
            elif key == "image":
                badge.set_status(image_status["status"], image_status["status"])

        self._refresh_onboarding()

    def _refresh_hero_state(self, llm: dict, image_status: dict) -> None:
        """SYSTEM STATE badge: only real signals decide the wording."""
        problems = []
        if llm["status"] == "offline" and self._settings.ai_enabled:
            problems.append("LLM OFFLINE")
        if image_status["status"] in ("unavailable", "offline"):
            problems.append("IMAGE OFFLINE")
        if not self._discovered_cameras:
            problems.append("NO CAMERA")
        if problems:
            self._hero_state_badge.set_status("error", "ISSUES")
            self._hero_state_detail.setText(" · ".join(problems[:3]))
        elif llm["status"] == "mock" or image_status["status"] == "mock":
            self._hero_state_badge.set_status("mock", "DEMO READY")
            self._hero_state_detail.setText("Mock providers active")
        else:
            self._hero_state_badge.set_status("ready", "NOMINAL")
            self._hero_state_detail.setText(
                "All systems operational"
            )

    def _refresh_recent_results(self) -> None:
        if not hasattr(self, "_home_results"):
            return
        while self._home_results.count():
            item = self._home_results.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        records = []
        for store in (self.image_store, self.uploads_store):
            records.extend(store.list(limit=200))
        records.sort(key=lambda r: r.timestamp, reverse=True)
        recent = records[:4]
        self._home_results_empty.setVisible(not recent)
        for record in recent:
            store = (
                self.uploads_store if record.source == "uploaded"
                else self.image_store
            )
            thumb = self._home_thumbnail(store, record)
            if thumb is not None:
                label = QLabel()
                label.setPixmap(thumb)
                label.setToolTip(f"{record.file}\n{record.prompt[:100]}")
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setStyleSheet(
                    "border: 1px solid #1a2836; border-radius: 6px;"
                )
                label.mousePressEvent = (
                    lambda _event, r=record: self._home_open_record(r)
                )
                self._home_results.addWidget(label)

    @staticmethod
    def _home_thumbnail(store: Optional[ImageStore], record: ImageRecord):
        if store is None:
            return None
        try:
            png_bytes = store.path_of(record).read_bytes()
        except OSError:
            return None
        pixmap = bytes_to_pixmap(png_bytes)
        if pixmap is None:
            return None
        return pixmap.scaled(
            120, 90, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _home_open_record(self, record: ImageRecord) -> None:
        self._select_record(record, self._store_for(record))
        self._goto_page("gallery")
        self.gallery_panel._show_detail(record)

    def _append_home_activity(self, text: str) -> None:
        if not hasattr(self, "_home_activity"):
            return
        self._home_activity.insertItem(0, text)
        while self._home_activity.count() > 12:
            self._home_activity.takeItem(self._home_activity.count() - 1)

    def _wire_signals(self) -> None:
        controller = self.controller
        controller.state_changed.connect(self._on_state_changed)
        controller.error_occurred.connect(self._on_error)
        controller.cameras_discovered.connect(self._on_cameras_discovered)
        controller.resolutions_probed.connect(self._on_resolutions_probed)
        controller.module_states_changed.connect(self._refresh_module_rows)
        controller.calibration_changed.connect(self._refresh_calibration_status)
        controller.scene_events.connect(self._on_scene_events)

        self.camera_panel.start_clicked.connect(self._on_start_clicked)
        self.camera_panel.stop_clicked.connect(self._on_stop_clicked)
        self.camera_panel.refresh_clicked.connect(controller.refresh_cameras_async)
        self.camera_panel.selection_changed.connect(self._on_camera_selection_changed)

        self.modules_panel.module_toggled.connect(self._on_module_toggled)
        self.modules_panel.setting_changed.connect(self._on_setting_changed)

        self.system_panel.setting_changed.connect(self._on_system_setting_changed)

        self.gaze_panel.calibrate_clicked.connect(self._open_calibration)
        self.gaze_panel.reset_calibration_clicked.connect(
            self.controller.reset_calibration
        )

        # Phase 6 wiring.
        self.preview_workspace.upload_button.clicked.connect(self._open_upload)
        self.analysis_tab_panel.upload_clicked.connect(self._open_upload)
        self.analysis_tab_panel.analyze_clicked.connect(self._analyze_selected)
        self.analysis_tab_panel.compare_clicked.connect(self._compare_selected)
        self.analysis_tab_panel.regenerate_clicked.connect(
            self._regenerate_with_feedback
        )
        self.analysis_tab_panel.feedback_submitted.connect(self._on_feedback)
        self.vision_panel.object_selected.connect(self._on_object_selected)
        self.gallery_panel.view_clicked.connect(self._gallery_view)
        self.gallery_panel.analyze_clicked.connect(self._gallery_analyze)
        self.gallery_panel.use_prompt_clicked.connect(self._gallery_use_prompt)
        self.gallery_panel.regenerate_clicked.connect(self._gallery_regenerate)
        self.gallery_panel.compare_clicked.connect(self._gallery_compare)
        self.image_panel.face_upload_clicked.connect(self._upload_face_reference)
        self.image_panel.face_remove_clicked.connect(self._remove_face_reference)
        self.image_panel.vary_clicked.connect(self._vary_selected)
        self.gallery_panel.inpaint_clicked.connect(self._gallery_inpaint)
        self.ai_panel.set_speak_handler(self._speak_answer)
        self.ai_panel.set_listen_handler(self._listen_query)
        stt = self.voice_engine.stt_status()
        self.ai_panel.set_stt_status(stt["status"], stt["detail"])
        self.ai_panel.set_memory(self.session_memory)
        self.ai_panel.set_extension_patterns(
            self.extension_registry.extra_command_patterns()
        )
        self.ai_panel.set_extension_handler(
            self.extension_registry.handle_command
        )
        voice = self.voice_engine.status()
        self.ai_panel.set_voice_status(voice["status"], voice["detail"])
        self.ai_panel.set_voice_auto(bool(self._settings.voice_enabled))
        self.system_panel.set_voice_status(voice["status"], voice["detail"])

        self._update_face_reference_state()
        # Workflow gating: nothing is selected on startup.
        self.analysis_tab_panel.set_feedback_enabled(False)
        # Inpaint capability gate (providers declare supports_inpainting).
        self.gallery_panel.set_inpaint_enabled(
            self.image_engine.capabilities_for().supports_inpainting
        )

    def _apply_initial_settings(self) -> None:
        settings = self._settings
        self.camera_panel.set_fps_target(settings.fps_target)
        set_debug(settings.debug_mode)
        self._refresh_calibration_status()
        self.vision_panel.setVisible(settings.vision_panel)
        # Non-blocking: provider probes run in a worker thread; the UI
        # shows real statuses as soon as the probe completes.
        self._refresh_provider_status(force=False)

    def _current_snapshot(self):
        """Latest SceneSnapshot for the AI/image panels."""
        with self.controller._latest_lock:
            result = self.controller._latest_result
        return result.scene if result is not None else None

    # ------------------------------------------------------------------
    # AI reaction engine (deterministic scene watches)
    # ------------------------------------------------------------------
    def _reaction_report(self, message: str) -> None:
        """Reaction watchers report here — appended to the chat."""
        self.ai_panel.append_system(message)
        self._append_home_activity(message[:90])

    # ------------------------------------------------------------------
    # Stage Mode (Phase 25)
    # ------------------------------------------------------------------
    def _toggle_stage(self) -> None:
        """Show/hide the frameless live-feed stage (F11)."""
        stage = getattr(self, "_stage_window", None)
        if stage is None:
            from app.ui.stage_window import StageWindow

            stage = StageWindow()
            self._stage_window = stage
        if stage.isVisible():
            stage.hide()
            return
        frame, result, stats = self.controller.latest()
        running = self.controller.is_running
        if frame is not None:
            stage.set_frame(frame)
        else:
            stage.set_placeholder(
                "STAGE MODE",
                "Start the camera — the live feed appears here."
                if not running else "STARTING CAMERA …",
            )
        stage.refresh_hud(
            stats.fps if running else 0.0, result, running, self._settings
        )
        stage.show()
        stage.raise_()

    # ------------------------------------------------------------------
    # Window-state memory (Phase 25)
    # ------------------------------------------------------------------
    def _save_window_state(self) -> None:
        """Persist size, position and the current page (on close)."""
        try:
            page = (
                self._page_keys[self._pages.currentIndex()]
                if self._page_keys else ""
            )
            self._settings_service.update(
                window_width=self.width(),
                window_height=self.height(),
                window_x=self.x(),
                window_y=self.y(),
                last_page=page,
            )
        except Exception:  # noqa: BLE001 — state save must never crash close
            log.debug("Could not persist window state")

    def _restore_window_state(self) -> None:
        """Restore size/position/page from the last session (validated)."""
        settings = self._settings
        try:
            width = int(settings.window_width)
            height = int(settings.window_height)
            if width >= self.minimumWidth() and height >= self.minimumHeight():
                self.resize(width, height)
            x = int(settings.window_x)
            y = int(settings.window_y)
            if -100_000 < x < 100_000 and -100_000 < y < 100_000:
                self.move(x, y)
            if settings.last_page and settings.last_page in self._page_keys:
                self._goto_page(settings.last_page)
        except (TypeError, ValueError):
            log.debug("Invalid stored window state — using defaults")

    def _speak_answer(self, text: str) -> None:
        """Local TTS for one AI answer (never blocks the GUI thread)."""
        self.voice_engine.speak_async(text)

    def _listen_query(self) -> None:
        """One-shot STT — result arrives on the GUI thread via the bridge."""

        def _done(text) -> None:
            if self._closing:
                return
            try:
                self._main_bridge.listen_result.emit(text)
            except RuntimeError:
                pass

        self.voice_engine.listen_async(_done)

    def _on_listen_result_gui(self, text) -> None:
        self.ai_panel.finish_listen(text)

    def _toggle_recording(self) -> None:
        if self.controller.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> str:
        if self.controller.recorder.is_recording:
            return "Already recording."
        try:
            path = self.controller.start_recording()
        except RuntimeError as exc:
            self.toasts.notify_error(
                "Could not start recording.",
                why=str(exc),
                fix="Start the camera first. MJPG/AVI fallback is automatic.",
                details=str(exc),
            )
            return f"Could not start recording: {exc}"
        if hasattr(self, "record_button"):
            self.record_button.setText("STOP REC")
        if hasattr(self, "_record_status"):
            self._record_status.setText(f"REC ● {path.name}")
        self.toasts.notify(f"Recording started — {path.name}", "success")
        self._append_home_activity(f"Recording started: {path.name}")
        return f"Recording started: {path.name}"

    def _stop_recording(self) -> str:
        info = self.controller.stop_recording("stopped")
        if hasattr(self, "record_button"):
            self.record_button.setText("RECORD")
        if info is None:
            if hasattr(self, "_record_status"):
                self._record_status.setText("")
            return "No recording was active."
        if hasattr(self, "_record_status"):
            self._record_status.setText(f"saved {info.path.name}")
        self.toasts.notify(
            f"Recording saved — {info.frames} frames · {info.duration_s:.1f}s",
            "success",
        )
        self._append_home_activity(f"Recording saved: {info.path.name}")
        return (
            f"Recording saved: {info.path.name} "
            f"({info.frames} frames, {info.duration_s:.1f}s)."
        )

    def _take_snapshot(self) -> str:
        try:
            path = self.controller.take_snapshot()
        except RuntimeError as exc:
            self.toasts.notify(str(exc), "warning")
            return str(exc)
        self.toasts.notify(f"Snapshot saved — {path.name}", "success")
        self._append_home_activity(f"Snapshot: {path.name}")
        return f"Snapshot saved: {path.name}"

    def _gallery_inpaint(self, record: ImageRecord) -> None:
        """Masked regeneration: provider inpaint with a chosen mask PNG.

        Capability-gated (the button only exists for providers with
        supports_inpainting). Mask convention: white = regenerate,
        black = keep. Everything stays local.
        """
        store = self._store_for(record)
        if store is None:
            return
        try:
            png_bytes = store.path_of(record).read_bytes()
        except OSError:
            self.toasts.notify_error(
                "Could not read the image file.",
                why="The stored image is missing or unreadable.",
                fix="Regenerate the image and try again.",
            )
            return
        mask_path, _filter = QFileDialog.getOpenFileName(
            self, "Choose mask (white = regenerate, black = keep)", "",
            "Mask (*.png *.jpg *.jpeg)",
        )
        if not mask_path:
            return
        try:
            import os as _os

            with open(_os.fsdecode(_os.fsencode(mask_path)), "rb") as handle:
                mask_bytes = handle.read()
        except OSError as exc:
            self.toasts.notify_error(
                "Could not read the mask file.",
                why=str(exc), fix="Choose a valid PNG mask and retry.",
                details=str(exc),
            )
            return
        prompt = self.image_panel.prompt_edit.toPlainText().strip() \
            or record.prompt or "inpaint"
        job = self.image_engine.inpaint(
            prompt,
            init_image=png_bytes,
            mask_image=mask_bytes,
            provider_key=self._settings.image_provider,
            version=record.version + 1,
            parent_id=record.file,
        )
        self._select_record(record, store)
        self._goto_page("create")
        self.activity_bar.set_queue_text(
            f"QUEUE: inpaint #{job.id} (v{job.version})"
        )
        self.toasts.notify("Inpainting queued.", "info")
        log.info("Inpaint job #%d enqueued from %s", job.id, record.file)

    def _handle_watch_request(self, target: str) -> str:
        """Start/stop a deterministic scene watch (offline-capable)."""
        if target == "stop":
            self.reaction_engine.clear()
            return "All watches stopped."
        return self.reaction_engine.watch(target)

    # ------------------------------------------------------------------
    # Scene capture (frozen snapshot actions)
    # ------------------------------------------------------------------
    def _capture_scene(self) -> None:
        snapshot = self._current_snapshot()
        if snapshot is None:
            self.toasts.notify(
                "No live scene to capture — start the camera first.", "warning"
            )
            return
        self._captured_snapshot = snapshot
        self._update_capture_buttons()
        self.toasts.notify("Scene captured.", "success")
        self._append_home_activity(
            f"Scene captured: {len(snapshot.objects)} objects, "
            f"{snapshot.persons} person(s)"
        )

    def _generate_from_scene(self) -> None:
        snapshot = self._captured_snapshot or self._current_snapshot()
        if snapshot is None:
            self.toasts.notify(
                "No scene available — capture one first.", "warning"
            )
            return
        from app.image.prompt_builder import build_scene_prompt

        prompt = build_scene_prompt(snapshot)
        if prompt is None:
            self.toasts.notify("Nothing detected in the scene.", "warning")
            return
        self.image_panel.prompt_edit.setPlainText(prompt)
        self.image_panel._on_generate()
        self.toasts.notify("Generation queued from scene.", "info")

    def _copy_scene(self) -> None:
        snapshot = self._captured_snapshot or self._current_snapshot()
        if snapshot is None:
            self.toasts.notify("No scene to copy.", "warning")
            return
        from app.ai.context import build_scene_context

        text = build_scene_context(snapshot)
        QApplication.clipboard().setText(text)
        self.toasts.notify("Scene description copied to clipboard.", "success")

    def _save_snapshot(self) -> None:
        snapshot = self._captured_snapshot
        if snapshot is None:
            self.toasts.notify("No captured scene to save.", "warning")
            return
        import json

        from dataclasses import asdict

        directory = data_dir() / "snapshots"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = directory / f"snapshot_{stamp}.json"
        path.write_text(
            json.dumps(asdict(snapshot), indent=2), encoding="utf-8"
        )
        self.toasts.notify(f"Snapshot saved: {path.name}", "success")

    def _update_capture_buttons(self) -> None:
        has_snapshot = self._captured_snapshot is not None
        for button in getattr(self, "_capture_buttons", []):
            button.setEnabled(has_snapshot)

    # ------------------------------------------------------------------
    # Object selection
    # ------------------------------------------------------------------
    def _on_object_selected(self, class_name: str, confidence: float,
                            object_id: int) -> None:
        self._selected_object = (class_name, confidence, object_id)
        self._object_selection_label.setText(
            f"{class_name.capitalize()} · {confidence * 100:.0f}%"
        )
        self.toasts.notify(f"Selected: {class_name}", "info")

    def _generate_object(self) -> None:
        if self._selected_object is None:
            self.toasts.notify(
                "Select an object in VISION ANALYSIS first.", "warning"
            )
            return
        class_name = self._selected_object[0]
        self.image_panel.prompt_edit.setPlainText(f"a {class_name}")
        self._goto_page("create")
        self.toasts.notify(f"Prompt set for: {class_name}", "info")

    def _copy_object_name(self) -> None:
        if self._selected_object is None:
            self.toasts.notify("Select an object first.", "warning")
            return
        QApplication.clipboard().setText(self._selected_object[0])
        self.toasts.notify("Object name copied.", "success")

    def _refresh_provider_status(self, force: bool = False) -> None:
        """Update provider status lines — never blocks the GUI thread.

        Uses cached probe results; starts a background probe when the
        cache is empty or ``force`` is set (explicit user refresh).
        """
        llm = self.ai_engine.provider_status_cached()
        image = self.image_engine.provider_status_cached()
        if llm is None:
            llm = self._last_llm_status
        if image is None:
            image = self._last_image_status
        if llm is not None and image is not None:
            self._apply_provider_statuses(llm, image)
        if force or llm is None or image is None:
            self._probe_providers_async()

    def _probe_providers_async(self) -> None:
        """Probe both providers in a worker thread (network calls!).

        The GUI thread never performs provider network I/O — results
        arrive via the main bridge.
        """
        if self._provider_probe_pending or self._closing:
            return
        self._provider_probe_pending = True

        def _work() -> None:
            try:
                llm = self.ai_engine.provider_status(force=True)
                image = self.image_engine.provider_status(force=True)
            except Exception:  # noqa: BLE001 — status must never crash
                log.exception("Provider status probe failed")
                llm = self._last_llm_status or {
                    "provider": self._settings.llm_provider,
                    "status": "offline", "detail": "probe failed",
                }
                image = self._last_image_status or {
                    "provider": self._settings.image_provider,
                    "status": "unavailable", "detail": "probe failed",
                }
            if not self._closing:
                try:
                    self._main_bridge.provider_statuses.emit((llm, image))
                except RuntimeError:
                    pass  # window teardown — receivers already gone

        threading.Thread(
            target=_work, name="provider-probe", daemon=True
        ).start()

    def _on_provider_statuses_gui(self, payload: tuple) -> None:
        """GUI thread: store + render the real provider statuses."""
        self._provider_probe_pending = False
        llm, image = payload
        self._last_llm_status = llm
        self._last_image_status = image
        self._apply_provider_statuses(llm, image)
        self._refresh_home()

    def _apply_provider_statuses(self, llm: dict, image: dict) -> None:
        """Render provider statuses into every panel (real values only)."""
        if llm["status"] == "online":
            self.ai_panel.set_status(f"LLM: ● ONLINE — {llm['detail']}")
            self.live_state_panel.set_ai_status("● ONLINE", ok=True)
            self.activity_bar.set_ai_status(f"LLM ● {llm['detail']}")
        elif llm["status"] == "mock":
            self.ai_panel.set_status(f"LLM: ● MOCK — {llm['detail']}")
            self.live_state_panel.set_ai_status("● MOCK", ok=True)
            self.activity_bar.set_ai_status(f"LLM ● {llm['detail']}")
        else:
            self.ai_panel.set_status(
                f"LLM: ● OFFLINE — {llm['detail']}", offline=True
            )
            self.live_state_panel.set_ai_status("● OFFLINE", ok=False)
            self.activity_bar.set_ai_status(f"LLM ● {llm['detail']}")
        # Render into the SYSTEM + CREATE panels (no re-probing).
        self.system_panel.set_statuses(llm, image)
        self.image_panel.set_status(image)
        capabilities = self.image_engine.capabilities_for()
        self.gallery_panel.set_inpaint_enabled(
            capabilities.supports_inpainting
        )
        self._refresh_storage_info()

    def _refresh_storage_info(self) -> None:
        import os

        capabilities = self.image_engine.capabilities_for()
        capability_names = []
        if capabilities.steps:
            capability_names.append("steps/cfg/seed")
        if capabilities.negative_prompt:
            capability_names.append("negative")
        if capabilities.models:
            capability_names.append("models")
        if capabilities.progress:
            capability_names.append("progress")
        if capabilities.supports_img2img:
            capability_names.append("img2img")
        if capabilities.supports_face_reference:
            capability_names.append("face-reference")
        capability_text = ", ".join(capability_names) or "basic only"

        self.system_panel.set_storage_info(
            data_directory=str(data_dir()),
            generated_count=len(self.image_store.list(limit=10_000)),
            uploads_count=len(self.uploads_store.list(limit=10_000)),
            key_configured=bool(os.environ.get("AI_VISION_LAB_API_KEY")),
            image_capabilities=capability_text,
            image_last_duration_ms=self.image_engine.last_duration_ms,
            image_last_error=self.image_engine.last_error or "",
            llm_last_duration_ms=self.ai_engine.last_llm_duration_ms,
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_cameras_discovered(self, cameras: list[CameraInfo]) -> None:
        self._discovered_cameras = cameras
        self.camera_panel.set_cameras(cameras)
        if cameras:
            wanted_index = self._settings.camera_index
            if not self.camera_panel.select_camera(wanted_index):
                self.camera_panel.select_camera(cameras[0].index)
            selected = self.camera_panel.selected_camera_index
            if selected is not None:
                self._refresh_resolutions_for(selected)
        else:
            self.video_widget.set_placeholder(
                "NO CAMERA DETECTED",
                "Please connect a webcam and press ⟳ to rescan.",
            )
            self.camera_panel.set_running(False)
        self._refresh_onboarding()

    def _refresh_resolutions_for(self, index: int) -> None:
        """(Re-)probe resolutions of a camera — async, keeps UI responsive."""
        self.controller.probe_resolutions_async(index)

    def _on_resolutions_probed(
        self, index: int, resolutions: list[tuple[int, int]]
    ) -> None:
        """Apply probe results, ignoring stale ones from a previous camera."""
        if self.camera_panel.selected_camera_index != index:
            return
        self.camera_panel.set_resolutions(resolutions)
        self.camera_panel.select_resolution(self._settings.resolution)

    def _on_camera_selection_changed(self) -> None:
        index = self.camera_panel.selected_camera_index
        if index is None:
            return
        self._settings_service.update(camera_index=index)
        self._refresh_resolutions_for(index)
        self._settings_service.update(
            resolution=self.camera_panel.selected_resolution,
            fps_target=self.camera_panel.selected_fps,
        )

    def _on_start_clicked(self) -> None:
        if self.camera_panel.selected_camera_index is None:
            self._show_error(
                "No camera detected",
                "Please connect a webcam first, then press ⟳ to rescan.",
            )
            return
        self._settings_service.update(
            camera_index=self.camera_panel.selected_camera_index,
            resolution=self.camera_panel.selected_resolution,
            fps_target=self.camera_panel.selected_fps,
        )
        self.controller.start_camera()

    def _on_stop_clicked(self) -> None:
        self.controller.stop_camera()

    def _on_state_changed(self, running: bool) -> None:
        self.header.set_live(running)
        self.camera_panel.set_running(running)
        self.status_panel.set_camera_state(running)
        self.live_state_panel.set_live(running)
        self.hud.set_live(running)
        stage = getattr(self, "_stage_window", None)
        if stage is not None:
            stage.hud.set_live(running)
            if not running:
                stage.set_placeholder(
                    "STAGE MODE", "Camera stopped — start it in the studio."
                )
        if running:
            self.video_widget.set_placeholder("STARTING CAMERA …")
            self.controller.reset_fps()
            self.gaze_panel.set_result(None, {}, running=True)
            self._append_home_activity("Camera started")
        else:
            self.status_panel.set_fps(0.0, 0.0)
            self.analysis_panel.set_result(None, tracking_active=False)
            self.gaze_panel.reset()
            self.inspector_panel.reset()
            self.vision_panel.set_result(None, running=False)
            self.video_widget.set_placeholder("WAITING FOR CAMERA")
            self.status_panel.set_resolution(0, 0)
            self.hud.reset()
            if hasattr(self, "pulse_panel"):
                self.pulse_panel.timeline.clear()
            if hasattr(self, "record_button"):
                self.record_button.setText("RECORD")
            if hasattr(self, "_record_status"):
                self._record_status.setText("")
            self._append_home_activity("Camera stopped")
        self._refresh_home()

    def _on_error(self, message: str) -> None:
        log.error("User-facing error: %s", message)
        self.camera_panel.set_error(message)
        from app.ui.errors import split_camera_error

        what, why, fix, details = split_camera_error(message)
        self.toasts.notify_error(what, why, fix, details)
        self._append_home_activity(f"Error: {message[:70]}")
        self._show_error("Camera error", message)

    def _on_module_toggled(self, key: str, enabled: bool) -> None:
        self.controller.set_module_enabled(key, enabled)

    def _on_system_setting_changed(self, key: str, value: object) -> None:
        """System panel settings that need runtime application."""
        if key == "vision_mode":
            self.controller.update_settings(vision_mode=value)
        elif key == "__reset__":
            # Settings were restored to defaults — apply what is
            # hot-applicable; the rest takes effect on restart.
            settings = self._settings_service.settings
            apply_theme(QApplication.instance(), bool(settings.dark_theme))
            self._apply_theme_visuals()
            set_debug(bool(settings.debug_mode))
            self.controller.update_settings(vision_mode=settings.vision_mode)
            self._refresh_provider_status(force=True)
            self.toasts.notify("Settings restored to defaults.", "success")
            self._append_home_activity("Settings reset to defaults")

    def _on_setting_changed(self, key: str, value: object) -> None:
        self.controller.update_settings(**{key: value})
        if key == "dark_theme":
            apply_theme(QApplication.instance(), bool(value))
            self._apply_theme_visuals()
        elif key == "debug_mode":
            set_debug(bool(value))
            log.info("Debug mode %s", "enabled" if value else "disabled")
        elif key == "vision_panel":
            self.vision_panel.setVisible(bool(value))
        elif key == "voice_enabled":
            self.ai_panel.set_voice_auto(bool(value))
        self._refresh_module_rows()

    def _refresh_module_rows(self) -> None:
        descriptors = self.controller.pipeline_descriptors()
        self.modules_panel.set_modules(
            descriptors, set(self.controller.pipeline.enabled_module_keys())
        )
        self._refresh_home()

    # ------------------------------------------------------------------
    # Gaze calibration
    # ------------------------------------------------------------------
    def _open_calibration(self) -> None:
        """Start the 9-point gaze calibration (requires a running camera)."""
        if not self.controller.is_running:
            self._show_error(
                "Calibration needs a camera",
                "Start the camera first, keep your face well lit and "
                "steady, then calibrate.",
            )
            return
        self._calibration_overlay = CalibrationOverlay(
            self.centralWidget(),
            feature_provider=self.controller.latest_features,
            screen_size=self.controller.actual_resolution(),
        )
        self._calibration_overlay.finished.connect(self._on_calibration_finished)
        self._calibration_overlay.show()
        self._calibration_overlay.raise_()
        self.gaze_panel.set_calibrating(True)

    def _on_calibration_finished(self, profile: Optional[CalibrationProfile]) -> None:
        self.gaze_panel.set_calibrating(False)
        self._calibration_overlay = None
        if profile is not None:
            self.controller.save_calibration(profile)
        self._refresh_calibration_status()

    def _refresh_calibration_status(self) -> None:
        self.gaze_panel.set_calibration_status(
            self.controller.calibration_status()
        )

    # ------------------------------------------------------------------
    # Scene events / AI auto summary
    # ------------------------------------------------------------------
    def _handle_image_intent(self) -> str:
        """AI -> image intent: build a scene prompt, optionally polish it
        with the LLM, and enqueue the generation.

        Runs in a worker thread (invoked from the AI panel). Works without
        any LLM: the deterministic prompt builder is the base line.
        """
        snapshot = self._current_snapshot()
        if snapshot is None:
            return (
                "I can't generate an image from the scene: no vision data "
                "available."
            )
        from app.image.prompt_builder import build_scene_prompt

        prompt = build_scene_prompt(snapshot)
        if prompt is None:
            return (
                "I can't generate an image from the scene: nothing was "
                "detected."
            )

        if self._settings.image_prompt_polish:
            polished = self._polish_image_prompt(prompt)
            if polished:
                prompt = polished

        preset = self._settings.image_preset
        job = self.image_engine.enqueue(
            prompt,
            provider_key=self._settings.image_provider,
            preset=preset,
        )
        preset_note = f" (preset {preset})" if preset != "none" else ""
        return (
            f"Image generation started as job #{job.id}{preset_note}.\n"
            f"Prompt: {prompt}"
        )

    def _handle_vision_intent(self, command: str) -> str:
        """Synchronous routing of image-analysis chat intents.

        Only triggers async work (analysis/generation run in their own
        workers) — the GUI thread never blocks here.
        """
        if command == "ANALYZE IMAGE":
            if self._selected_record_bytes() is None:
                return "No image selected — pick one in the GALLERY first."
            self._analyze_selected()
            return "Analysis started for the selected image."
        if command == "COMPARE IMAGES":
            if self._selected_record_bytes() is None:
                return "No image selected — pick one in the GALLERY first."
            self._compare_selected()
            return "Comparison prepared in the COMPARE tab."
        if command == "IMPROVE IMAGE":
            if self._selected_record_bytes() is None:
                return "No image selected — pick one in the GALLERY first."
            self._regenerate_with_feedback()
            return "Regeneration with your feedback has been queued."
        if command == "GENERATE VARIANT":
            if self._selected_record_bytes() is None:
                return "No image selected — pick one in the GALLERY first."
            self._vary_selected()
            return "Image-to-image variation has been queued."
        if command == "WHAT CHANGED?":
            return self._diff_last_versions()
        if command == "START RECORDING":
            return self._start_recording()
        if command == "STOP RECORDING":
            return self._stop_recording()
        if command == "TAKE SNAPSHOT":
            return self._take_snapshot()
        if command == "SESSION RECAP":
            state = self.controller.analytics_state()
            from app.session.recap import build_session_recap

            return build_session_recap(
                duration_s=float(state["duration_s"]),
                blink_stats=state["blinks"],
                gaze_samples=int(state["gaze_samples"]),
                gaze_coverage=float(state["gaze_coverage"]),
                events=state["events"],
                now_running=self.controller.is_running,
            )
        if command == "CAPTURE AND GENERATE":
            snapshot = self._current_snapshot()
            if snapshot is None:
                return (
                    "I can't capture a scene: no vision data available. "
                    "Start the camera first."
                )
            from app.image.prompt_builder import build_scene_prompt

            prompt = build_scene_prompt(snapshot)
            if prompt is None:
                return "Nothing was detected in the scene — nothing to generate."
            self._captured_snapshot = snapshot
            self._update_capture_buttons()
            self.image_panel.prompt_edit.setPlainText(prompt)
            job = self.image_engine.enqueue(
                prompt,
                provider_key=self._settings.image_provider,
                preset=self._settings.image_preset,
            )
            return (
                f"Scene captured and generation queued as job "
                f"#{job.id}.\nPrompt: {prompt}"
            )
        return f"Command '{command}' has no handler."

    def _diff_last_versions(self) -> str:
        """Deterministic v1-vs-v2 comparison from stored analyses."""
        generated = sorted(
            self.image_store.list(limit=500),
            key=lambda r: (r.parent_id or r.file, r.version),
        )
        candidates = [r for r in generated if r.analysis is not None]
        if len(candidates) < 2:
            return (
                "I can't compare yet: at least two analyzed versions are "
                "needed."
            )
        newer, older = candidates[-1], candidates[-2]
        new_objects = set(newer.analysis.get("objects", []))
        old_objects = set(older.analysis.get("objects", []))
        added = sorted(new_objects - old_objects)
        removed = sorted(old_objects - new_objects)

        def verdict_of(record) -> str:
            match = record.analysis.get("prompt_match", {})
            return match.get("verdict", "unable to determine")

        parts = [
            f"Comparing {older.file} (v{older.version}) with "
            f"{newer.file} (v{newer.version}):",
        ]
        if added:
            parts.append("Newly detected: " + ", ".join(added) + ".")
        if removed:
            parts.append("No longer detected: " + ", ".join(removed) + ".")
        if not added and not removed:
            parts.append("Detected content is unchanged.")
        parts.append(
            f"Prompt match: {verdict_of(older)} -> {verdict_of(newer)}."
        )
        return " ".join(parts)

    def start_demo(self):
        """Run the scripted demo on the main thread (pumps the event loop).

        Returns the completed step list; the app stays responsive because
        every poll processes queued Qt events.
        """
        from app.demo.overlay import DemoOverlay
        from app.demo.runner import DemoRunner

        self._demo_overlay = DemoOverlay(self.centralWidget())
        self._demo_runner = DemoRunner(
            self, on_step=self._demo_overlay.update_step
        )
        self._demo_overlay.set_steps(self._demo_runner.steps)
        self._demo_overlay.show()
        # Title suffix exactly once; restored after the run (a repeated
        # demo must never append " — DEMO MODE" again).
        self._base_window_title = self.windowTitle()
        self.setWindowTitle(f"{self._base_window_title} — DEMO MODE")
        steps = self._demo_runner.run()
        self._demo_overlay.update_step(None)  # final summary card
        if self._demo_runner.completed:
            self.toasts.notify("Demo complete — all steps passed.", "success")
        else:
            self.toasts.notify(
                "Demo finished with failures — see the summary.", "warning"
            )
        # Keep the summary visible for a few seconds, then dismiss it.
        QTimer.singleShot(4500, self._demo_overlay.hide)
        self.setWindowTitle(
            getattr(self, "_base_window_title", "") or self.windowTitle()
        )
        return steps

    def _polish_image_prompt(self, base_prompt: str) -> Optional[str]:
        """Optional LLM polish of the deterministic scene prompt.

        The LLM only sees the prompt text (never camera data). On any
        error the deterministic prompt is used unchanged.
        """
        try:
            result: dict = {}
            done = threading.Event()

            def on_done(text: str) -> None:
                result["text"] = text
                done.set()

            self.ai_engine.ask(
                "Rewrite the following image-generation prompt so it is "
                "more descriptive while keeping exactly the same content "
                "and the same style constraints. Reply with only the "
                f"prompt text:\n\n{base_prompt}",
                self._current_snapshot(),
                on_done=on_done,
                on_error=lambda _message: done.set(),
            )
            done.wait(timeout=20.0)
            text = result.get("text", "").strip()
            if not text or text.startswith("[MOCK]"):
                return None
            return text
        except Exception:  # noqa: BLE001 — polish is optional
            log.exception("Prompt polishing failed — using base prompt")
            return None

    def _on_scene_events(self, events: list) -> None:
        """Feed scene changes into the chat and (optionally) auto-summarize."""
        if not self._settings.ai_enabled:
            return
        for event in events:
            if event.type is EventType.SCENE_CHANGED:
                continue  # implied by the concrete events
            formatted = self._format_event(event)
            self.ai_panel.append_event(formatted)
            self.activity_bar.set_event(formatted)

        if not self._settings.vision_auto_summary:
            return
        changed = any(
            event.type is EventType.SCENE_CHANGED for event in events
        )
        if not changed:
            return
        import time as _time

        now = _time.monotonic()
        if now - self._last_auto_summary < _AUTO_SUMMARY_MIN_INTERVAL:
            return
        self._last_auto_summary = now
        snapshot = self._current_snapshot()
        if snapshot is None:
            return
        self.ai_panel.submit(
            "Briefly summarize the current scene in one or two sentences."
        )

    @staticmethod
    def _format_event(event) -> str:
        details = event.details
        if event.type is EventType.OBJECT_APPEARED:
            return f"OBJECT_APPEARED: {details.get('object', '?')}"
        if event.type is EventType.OBJECT_DISAPPEARED:
            return f"OBJECT_DISAPPEARED: {details.get('object', '?')}"
        if event.type is EventType.PERSON_APPEARED:
            return f"PERSON_APPEARED (persons now: {details.get('count', '?')})"
        if event.type is EventType.PERSON_LEFT:
            return f"PERSON_LEFT (persons now: {details.get('count', '?')})"
        if event.type is EventType.GESTURE_CHANGED:
            return (
                f"GESTURE_CHANGED: from {details.get('from')} "
                f"to {details.get('to')}"
            )
        if event.type is EventType.GAZE_CHANGED:
            return f"GAZE_CHANGED: from {details.get('from')} to {details.get('to')}"
        return str(event.type.value)

    # ------------------------------------------------------------------
    # Phase 6: upload / analysis / feedback / iteration
    # ------------------------------------------------------------------
    def _open_upload(self) -> None:
        """File dialog for PNG/JPG/WEBP; local analysis only."""
        path, _filter = QFileDialog.getOpenFileName(
            self, "Upload image", "", _UPLOAD_FILTER
        )
        if not path:
            return
        try:
            import os

            size = os.path.getsize(os.fsdecode(os.fsencode(path)))
            if size > _MAX_UPLOAD_BYTES:
                self._show_error(
                    "Upload failed",
                    f"The file is {size / 1e6:.1f} MB — the limit is "
                    f"{_MAX_UPLOAD_BYTES / 1e6:.0f} MB. Please choose a "
                    "smaller image.",
                )
                return
            with open(os.fsdecode(os.fsencode(path)), "rb") as handle:
                png_bytes = handle.read()
        except OSError as exc:
            self.analysis_tab_panel.set_result(None)
            self._show_error("Upload failed", f"Could not read file: {exc}")
            return

        array = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            self._show_error(
                "Upload failed",
                "Unsupported or corrupt image. Supported: PNG, JPG, WEBP.",
            )
            return

        record = ImageRecord(
            file="",
            timestamp=time.time(),
            provider="upload",
            prompt="",
            width=image.shape[1],
            height=image.shape[0],
            source="uploaded",
        )
        try:
            record = self.uploads_store.save(record, png_bytes)
        except OSError as exc:
            self._show_error("Upload failed", f"Could not store image: {exc}")
            return

        self._select_record(record, self.uploads_store)
        self.preview_workspace.show_upload(
            png_bytes,
            f"Uploaded {record.file} ({image.shape[1]}×{image.shape[0]})",
        )
        self.preview_workspace.tabs.setCurrentIndex(1)
        self.analysis_tab_panel.set_result(None)
        self.gallery_panel.refresh()
        self._refresh_recent_results()
        self.toasts.notify(
            f"Image uploaded — {image.shape[1]}×{image.shape[0]}", "success"
        )
        self._append_home_activity(f"Uploaded {record.file}")
        log.info("Image uploaded: %s", record.file)

    def _select_record(
        self, record: Optional[ImageRecord], store: Optional[ImageStore]
    ) -> None:
        self._selected_record = record
        self._selected_store = store
        # Workflow gating: feedback only makes sense with a selection.
        self.analysis_tab_panel.set_feedback_enabled(record is not None)

    def _selected_record_bytes(self) -> Optional[tuple[ImageRecord, bytes]]:
        record = self._selected_record
        store = self._selected_store
        if record is None or store is None:
            return None
        try:
            return record, store.path_of(record).read_bytes()
        except OSError:
            return None

    # ------------------------------------------------------------------
    def _analyze_selected(self) -> None:
        selected = self._selected_record_bytes()
        if selected is None:
            self.analysis_tab_panel.set_result(None)
            self._show_error(
                "Nothing to analyze",
                "Select an uploaded or generated image first (GALLERY tab).",
            )
            return
        record, png_bytes = selected
        array = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            self.analysis_tab_panel.set_result(None)
            self._show_error("Analysis failed", "Corrupt image data.")
            return
        self._run_analysis(
            image, record, prompt=record.prompt or None,
            store=self._selected_store,
        )

    def _run_analysis(
        self,
        image: np.ndarray,
        record: Optional[ImageRecord],
        prompt: Optional[str] = None,
        snapshot=None,
        store: Optional[ImageStore] = None,
    ) -> None:
        """Local analysis in a worker thread; result attached to the record.

        The result travels back via the main bridge (queued to the GUI
        thread) — the worker never touches widgets directly. Deleting the
        record while the analysis runs is safe: the store update simply
        has no target and returns False.
        """
        self.analysis_tab_panel.set_analyzing(True)

        def on_done(result: ImageAnalysisResult) -> None:
            if record is not None and store is not None:
                record.analysis = result.to_dict()
                store.update(record)  # no-op (False) if deleted meanwhile
            self._main_bridge.analysis_result.emit((result, record))

        def on_error(message: str) -> None:
            self._main_bridge.analysis_result.emit((None, record, message))

        self.analysis_engine.analyze_async(
            image,
            source=record.source if record else "generated",
            prompt=prompt,
            snapshot=snapshot,
            on_done=on_done,
            on_error=on_error,
        )

    def _on_analysis_result_gui(self, payload: tuple) -> None:
        """GUI-thread: render the analysis result + live pipeline status."""
        result = payload[0]
        record = payload[1] if len(payload) > 1 else None
        if result is None:
            message = payload[2] if len(payload) > 2 else "analysis failed"
            self.analysis_tab_panel.set_analyzing(False, f"ANALYSIS FAILED — {message[:60]}")
            self.toasts.notify_error(
                "Analysis failed.",
                why=message[:100],
                fix="Check the image file and try again.",
                details=message,
            )
            return
        self.analysis_tab_panel.set_result(result)
        self.gallery_panel.refresh()
        self.toasts.notify("Analysis complete.", "success")
        self._append_home_activity(
            f"Analysis: {result.source} · {result.confidence * 100:.0f}%"
        )

        # Live pipeline status in the center workspace (honest verdict).
        if (
            record is not None
            and record.file == self._last_generated_file
            and self._last_result_info
        ):
            verdict = (
                result.prompt_match.verdict
                if result.prompt_match.checked
                else "analyzed"
            )
            self.preview_workspace.show_result_info(
                f"{self._last_result_info} · ANALYZED — {verdict}"
            )
            self.live_state_panel.set_image_status("● ANALYZED", ok=True)

    def _on_job_status_gui(self, job) -> None:
        """GUI-thread job status: panel updates, preview, auto analysis."""
        self.image_panel.on_job_status(job)
        self.activity_bar._on_job_status(job)

        if job.status == GENERATING:
            self.preview_workspace.show_result_info(
                f"GENERATING — {format_job_status(job)}"
            )
            self.live_state_panel.set_image_status("● GENERATING", ok=True)
            self._create_result_status.set_status("processing", "GENERATING")
            self._create_processing.setText(
                format_job_status(job)
                if job.progress is not None
                else "Provider does not report progress — please wait."
            )
        if job.status == "FAILED":
            self.live_state_panel.set_image_status("● FAILED", ok=False)
            self._create_result_status.set_status("error", "FAILED")
            self._create_processing.setText("")
            from app.ui.errors import split_provider_error

            what, why, fix, details = split_provider_error(
                job.provider_key, job.error or ""
            )
            self.toasts.notify_error(what, why, fix, details)
            self._append_home_activity(f"Generation job #{job.id} FAILED")
        if job.status == "COMPLETED" and job.result is not None:
            self._update_create_actions()
            info = (
                f"#{job.id} · {job.result.provider}"
                + (" [MOCK]" if job.result.is_mock else "")
                + f" · {job.result.width}×{job.result.height}"
                + (f" · v{job.version}" if job.version > 1 else "")
            )
            if job.record is not None:
                self._last_generated_file = job.record.file
            self._last_result_info = info
            self.preview_workspace.show_result(job.result.png_bytes, info)

            # CREATE page: big result preview + info line.
            pixmap = bytes_to_pixmap(job.result.png_bytes)
            self._create_preview.set_pixmap_scaled(pixmap)
            self._create_info.setText(info)
            self._create_result_status.set_status("ready", "COMPLETE")
            self._create_processing.setText("")
            record_lines = [info]
            if job.record is not None:
                record_lines.append(f"file: {job.record.file}")
            if job.duration_ms:
                record_lines.append(f"duration: {job.duration_ms:.0f} ms")
            self._create_result_info.setText("\n".join(record_lines))

            self.gallery_panel.refresh()
            self._refresh_recent_results()
            self.toasts.notify(f"Generation complete — job #{job.id}", "success")
            self._append_home_activity(
                f"Generated: {job.result.provider}"
                + (" [MOCK]" if job.result.is_mock else "")
                + f" · v{job.version}"
            )
            # Auto-analyze exactly once per completed job.
            if (
                self._settings.auto_analyze_generated
                and job.id not in self._analyzed_jobs
            ):
                self._analyzed_jobs.add(job.id)
                self.preview_workspace.show_result_info(
                    f"{info} · ANALYZING…"
                )
                array = np.frombuffer(job.result.png_bytes, dtype=np.uint8)
                image = cv2.imdecode(array, cv2.IMREAD_COLOR)
                if image is not None and job.record is not None:
                    self._run_analysis(
                        image,
                        job.record,
                        prompt=job.record.prompt or None,
                        snapshot=self._current_snapshot(),
                        store=self.image_store,
                    )

    def _update_face_reference_state(self) -> None:
        self.image_panel.set_face_reference_state(
            active=bool(self._settings.face_reference_enabled),
            path_exists=self._face_reference_path.exists(),
        )

    def _upload_face_reference(self) -> None:
        """Optional face photo for generation — stored locally ONLY.

        No provider currently supports face reference; the photo is
        stored locally and clearly never sent anywhere automatically.
        """
        path, _filter = QFileDialog.getOpenFileName(
            self, "Upload face photo", "", _UPLOAD_FILTER
        )
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            self._show_error("Upload failed", f"Could not read file: {exc}")
            return
        array = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            self._show_error("Upload failed", "Unsupported or corrupt image.")
            return
        try:
            self._face_reference_path.parent.mkdir(parents=True, exist_ok=True)
            ok, png = cv2.imencode(".png", image)
            if not ok:
                raise OSError("encoding failed")
            self._face_reference_path.write_bytes(png.tobytes())
        except OSError as exc:
            self._show_error("Upload failed", f"Could not store face photo: {exc}")
            return
        self._settings_service.update(face_reference_enabled=True)
        self._update_face_reference_state()
        log.info("Face reference photo stored locally (never sent anywhere)")

    def _remove_face_reference(self) -> None:
        try:
            self._face_reference_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._settings_service.update(face_reference_enabled=False)
        self._update_face_reference_state()
        log.info("Face reference photo removed")

    def _vary_selected(self) -> None:
        """img2img variation of the selected gallery record."""
        selected = self._selected_record_bytes()
        if selected is None:
            self._show_error(
                "Nothing selected",
                "Select a generated or uploaded image in the GALLERY first.",
            )
            return
        record, png_bytes = selected
        prompt = self.image_panel.prompt_edit.toPlainText().strip() or record.prompt
        if not prompt:
            self._show_error("No prompt", "The selected image has no prompt.")
            return
        job = self.image_engine.enqueue(
            prompt,
            provider_key=self._settings.image_provider,
            preset=self._settings.image_preset,
            init_image=png_bytes,
            version=record.version + 1,
            parent_id=record.file,
        )
        self._goto_page("create")
        self.activity_bar.set_queue_text(
            f"QUEUE: img2img #{job.id} (v{job.version})"
        )
        log.info("img2img job #%d enqueued from %s", job.id, record.file)

    def _on_feedback(self, rating: str, category: str = "", text: str = "") -> None:
        """Store feedback on the selected record (used on regeneration).

        The category (feedback 3.0) is stored as a ``[category]`` tag in
        the feedback text so refine_prompt() can map it deterministically.
        """
        selected = self._selected_record_bytes()
        if selected is None:
            return
        record, _png = selected
        import time as _time

        tagged = f"[{category}] {text}".strip() if category else text
        record.feedback.append(
            FeedbackEntry(
                rating=rating, text=tagged, timestamp=_time.time()
            ).to_dict()
        )
        if self._selected_store is not None:
            self._selected_store.update(record)
        log.info(
            "Feedback stored on %s (%s): %s", record.file, rating, text[:80]
        )
        self.gallery_panel.refresh()
        self.toasts.notify(
            f"Feedback applied ({rating.upper()})", "success"
        )
        self._append_home_activity(
            f"Feedback on {record.file}: {rating}"
        )

    def _regenerate_with_feedback(self) -> None:
        """Iterative generation: feedback -> refined prompt -> new version."""
        selected = self._selected_record_bytes()
        if selected is None:
            self._show_error(
                "Nothing to regenerate",
                "Select an image with feedback in the GALLERY first.",
            )
            return
        record, png_bytes = selected
        entries = [
            entry
            for entry in (
                FeedbackEntry.from_dict(raw) for raw in record.feedback
            )
            if entry is not None
        ]
        if not entries:
            self._show_error(
                "No feedback yet",
                "Rate the image (CORRECT/WRONG/PARTIAL) or add text "
                "feedback first.",
            )
            return
        refined = refine_prompt(
            record.prompt or "", entries, self._current_snapshot()
        )
        job = self.image_engine.enqueue(
            refined,
            provider_key=self._settings.image_provider,
            preset=self._settings.image_preset,
            version=record.version + 1,
            parent_id=record.file,
        )
        self._select_record(record, self._selected_store)
        self._goto_page("create")  # GENERATE
        self.activity_bar.set_queue_text(
            f"QUEUE: regeneration #{job.id} (v{job.version})"
        )
        log.info("Regeneration v%d enqueued from %s", job.version, record.file)

    # ------------------------------------------------------------------
    # Gallery actions
    # ------------------------------------------------------------------
    def _gallery_view(self, record: ImageRecord) -> None:
        store = self._store_for(record)
        if store is None:
            return
        self._select_record(record, store)
        try:
            png_bytes = store.path_of(record).read_bytes()
        except OSError:
            return
        info = f"{record.file} · {record.source} · {record.width}×{record.height}"
        if record.analysis is not None:
            confidence = record.analysis.get("confidence")
            if confidence is not None:
                info += f" · analyzed {confidence * 100:.0f}%"
        self.preview_workspace.show_result(png_bytes, info)
        self.preview_workspace.tabs.setCurrentIndex(0)
        self._show_analysis_if_present(record)

    def _gallery_analyze(self, record: ImageRecord) -> None:
        store = self._store_for(record)
        if store is None:
            return
        self._select_record(record, store)
        try:
            png_bytes = store.path_of(record).read_bytes()
        except OSError:
            return
        array = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            return
        self._run_analysis(
            image, record, prompt=record.prompt or None,
            snapshot=self._current_snapshot(),
            store=store,
        )

    def _gallery_use_prompt(self, record: ImageRecord) -> None:
        self._goto_page("create")
        self.image_panel.prompt_edit.setPlainText(record.prompt)
        self.image_panel.negative_edit.setPlainText(record.negative_prompt)

    def _gallery_regenerate(self, record: ImageRecord) -> None:
        self._select_record(record, self._store_for(record))
        job = self.image_engine.enqueue(
            record.prompt,
            provider_key=self._settings.image_provider,
            preset=self._settings.image_preset,
            version=record.version + 1,
            parent_id=record.file,
        )
        self._goto_page("create")
        self.activity_bar.set_queue_text(
            f"QUEUE: regenerate #{job.id} (v{job.version})"
        )

    def _gallery_compare(self, record: ImageRecord) -> None:
        store = self._store_for(record)
        if store is None:
            return
        self._select_record(record, store)
        self._compare_selected()

    def _store_for(self, record: ImageRecord) -> Optional[ImageStore]:
        if record.source == "uploaded":
            return self.uploads_store
        return self.image_store

    def _show_analysis_if_present(self, record: ImageRecord) -> None:
        if record.analysis:
            self.analysis_tab_panel.set_result(
                ImageAnalysisResult.from_dict(record.analysis),
                source=record.file,
            )
        else:
            self.analysis_tab_panel.set_result(None)

    def _compare_selected(self) -> None:
        """Generated vs. its analysis reference (uploaded or previous)."""
        selected = self._selected_record_bytes()
        if selected is None:
            self._show_error(
                "Nothing to compare", "Select an image in the GALLERY first."
            )
            return
        record, png_bytes = selected
        pixmap_a = bytes_to_pixmap(png_bytes)

        pixmap_b = None
        if record.parent_id:
            parent_store = self._store_for(record)
            parent_bytes = None
            if parent_store is not None:
                parent_bytes = self._read_record_bytes(parent_store, record.parent_id)
            if parent_bytes is not None:
                pixmap_b = bytes_to_pixmap(parent_bytes)
        elif record.source == "generated" and self._settings.camera_index >= 0:
            # Compare against the last uploaded image if any.
            uploads = self.uploads_store.list(limit=1)
            if uploads:
                try:
                    pixmap_b = bytes_to_pixmap(
                        self.uploads_store.path_of(uploads[0]).read_bytes()
                    )
                except OSError:
                    pixmap_b = None

        self.preview_workspace.show_compare(
            pixmap_a, pixmap_b,
            label_a=self._compare_caption(record),
            label_b=self._compare_caption_other(record),
            meta_a=self._compare_meta(record),
            meta_b=self._compare_meta_other(record),
        )
        self.preview_workspace.tabs.setCurrentIndex(2)

    @staticmethod
    def _compare_meta(record: ImageRecord) -> str:
        parts = [record.prompt[:70]]
        if record.analysis:
            match = record.analysis.get("prompt_match", {})
            verdict = match.get("verdict")
            score = match.get("score")
            if verdict:
                parts.append(verdict + (f" {score * 100:.0f}%" if score is not None else ""))
            parts.append(f"confidence {record.analysis.get('confidence', 0) * 100:.0f}%")
        if record.feedback:
            parts.append(
                "feedback: " + ", ".join(
                    entry.get("rating", "?") for entry in record.feedback
                )
            )
        return " · ".join(parts)

    def _compare_meta_other(self, record: ImageRecord) -> str:
        if record.parent_id:
            parent = self._read_record_bytes(self.image_store, record.parent_id)
            if parent is not None:
                parent_record = self.image_store.get(record.parent_id)
                if parent_record is not None:
                    return self._compare_meta(parent_record)
            return "previous version"
        uploads = self.uploads_store.list(limit=1)
        if uploads:
            return f"upload · {uploads[0].file}"
        return "reference"

    def _compare_caption(self, record: ImageRecord) -> str:
        badge = " [MOCK]" if record.is_mock else ""
        version = f" · v{record.version}" if record.version > 1 else ""
        return f"{record.source.upper()}{version}{badge}"

    def _compare_caption_other(self, record: ImageRecord) -> str:
        if record.parent_id:
            return "PREVIOUS VERSION"
        if record.source == "generated":
            uploads = self.uploads_store.list(limit=1)
            if uploads:
                return f"UPLOAD · {uploads[0].file}"
        return "REFERENCE"

    @staticmethod
    def _read_record_bytes(store: ImageStore, file_name: str) -> Optional[bytes]:
        try:
            return (store.directory / file_name).read_bytes()
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def _poll_frame(self) -> None:
        if self._closing:
            return
        frame, result, stats = self.controller.latest()
        running = self.controller.is_running
        if running:
            self.status_panel.set_fps(stats.fps, stats.frame_time_ms)
            self.status_panel.set_resolution(*self.controller.actual_resolution())
            self.live_state_panel.set_fps(stats.fps)
        if frame is not None:
            self.video_widget.set_frame(frame)
            stage = getattr(self, "_stage_window", None)
            if stage is not None and stage.isVisible():
                stage.set_frame(frame)
        if result is not None:
            self.analysis_panel.set_result(
                result,
                tracking_active=(
                    running and self._settings.face_mesh
                ),
            )
            self.gaze_panel.set_result(
                result,
                self.controller.session_stats(),
                running=running,
            )
            self.vision_panel.set_result(
                result, running=running
            )
            self.live_state_panel.set_result(
                result, running=running
            )
            self.inspector_panel.set_result(
                result,
                running=running,
                fps=stats.fps if running else 0.0,
                frame_time_ms=stats.frame_time_ms
                if running else 0.0,
                delegate_summary=self._cached_delegate,
                generation_status=self._cached_generation_status,
            )

        # HUD + cheap caches: 2 Hz (never in the 30 Hz path).
        now = time.monotonic()
        if now - getattr(self, "_last_hud_refresh", 0.0) > 0.5:
            self._last_hud_refresh = now
            self._refresh_hud(stats.fps if running else 0.0, result, running)
            self._refresh_pulse()
            self._refresh_insights()
            self._handle_gesture_actions(result)

        # AI reaction watches (deterministic, internal cooldowns).
        snapshot = self._current_snapshot()
        if snapshot is not None:
            self.reaction_engine.update(snapshot)

        # Home dashboard: throttled refresh (real values only).
        if now - getattr(self, "_last_home_refresh", 0.0) > 0.5:
            self._last_home_refresh = now
            self._refresh_home()

    def _refresh_pulse(self) -> None:
        """Feed the scene-pulse timelines (VISION + INSIGHTS) with the
        controller's bounded event list."""
        events = self.controller.recent_events()
        if hasattr(self, "pulse_panel"):
            self.pulse_panel.timeline.set_events(events)
        insights = getattr(self, "insights_panel", None)
        if insights is not None:
            insights.pulse.timeline.set_events(events)

    def _refresh_insights(self) -> None:
        """Feed the INSIGHTS page (only while it exists; values are
        cheap — bounded session state)."""
        insights = getattr(self, "insights_panel", None)
        if insights is None:
            return
        state = self.controller.analytics_state()
        width = max(1, self.video_widget.width())
        height = max(1, self.video_widget.height())
        state["heatmap_overlay"] = self.controller.heatmap_snapshot(
            width, height
        )
        state["now"] = time.monotonic()
        insights.update_state(state)

    def _handle_gesture_actions(self, result) -> None:
        """Phase 26: OPEN PALM = capture scene, FIST = toggle HUD.

        Gated by the gesture_actions setting, per-gesture cooldown
        (3 s) and a confirmation toast — real gestures only, no
        accidental double-triggers.
        """
        if (
            result is None
            or not self.controller.is_running
            or not self._settings.gesture_actions
        ):
            return
        now = time.monotonic()
        for gesture in result.gestures:
            name = str(getattr(gesture, "gesture", "")).replace("_", " ").strip().upper()
            if name == "OPEN PALM" and now - self._gesture_last_open_palm >= 3.0:
                self._gesture_last_open_palm = now
                snapshot = self._current_snapshot()
                if snapshot is not None:
                    self._captured_snapshot = snapshot
                    self._update_capture_buttons()
                    self.toasts.notify(
                        "GESTURE: scene captured (open palm).", "success"
                    )
                    self._append_home_activity(
                        "Gesture action: scene captured"
                    )
            elif name == "FIST" and now - self._gesture_last_fist >= 3.0:
                self._gesture_last_fist = now
                visible = not self.hud.isVisible()
                self.hud.set_visible(visible)
                self.toasts.notify(
                    f"GESTURE: HUD {'shown' if visible else 'hidden'} "
                    "(fist).",
                    "info",
                )

    def _refresh_hud(self, fps: float, result, running: bool) -> None:
        """Update the live HUD overlay(s) with real values only."""
        from app.ui.hud import update_hud_from_state

        update_hud_from_state(
            self.hud, fps, result, running, self._settings
        )
        stage = getattr(self, "_stage_window", None)
        if stage is not None and stage.isVisible():
            stage.refresh_hud(fps, result, running, self._settings)

    def _generation_status_text(self) -> str:
        jobs = self.image_engine.queue.active_jobs(limit=1)
        if not jobs:
            return "idle"
        return jobs[0].status.lower()

    def _poll_stats(self) -> None:
        if self._closing:
            return
        self.status_panel.set_performance(
            self._monitor.cpu_percent(), self._monitor.memory_mb()
        )
        # 1 Hz cache refresh — delegate + generation status are stable
        # between ticks and must not cost 30 fps of dict churn.
        self._cached_delegate = self.controller.delegate_summary()
        self._cached_generation_status = self._generation_status_text()
        self._refresh_recording_status()

    def _refresh_recording_status(self) -> None:
        """Keep RECORD / STOP REC honest if the recorder auto-stops."""
        if not hasattr(self, "record_button"):
            return
        recorder = self.controller.recorder
        if recorder.is_recording:
            status = recorder.status()
            self.record_button.setText("STOP REC")
            if hasattr(self, "_record_status"):
                self._record_status.setText(
                    f"REC ● {status['elapsed_s']:.0f}s · {status['frames']} f"
                )
            return
        if self.record_button.text() == "STOP REC":
            self.record_button.setText("RECORD")
            if hasattr(self, "_record_status"):
                self._record_status.setText("auto-stopped (limit reached)")

    # ------------------------------------------------------------------
    # Vision modules
    # ------------------------------------------------------------------
    def load_vision_modules_now(self) -> None:
        """Public deferred entry (startup): load modules and update state.

        Called by ``main.py`` via ``QTimer.singleShot`` so the window is
        already visible while models initialize.
        """
        self._load_vision_modules()

    def _load_vision_modules(self) -> None:
        errors = self.controller.load_vision_modules()
        self._refresh_module_rows()
        delegate_summary = self.controller.delegate_summary()
        self._cached_delegate = delegate_summary
        self.system_panel.set_delegate_summary(delegate_summary)
        self.live_state_panel.set_delegate(delegate_summary)
        self._refresh_storage_info()
        if errors:
            # One aggregated, structured dialog instead of N modals.
            self._show_module_errors(errors)
        else:
            if self.controller.is_running:
                self.video_widget.set_placeholder("STARTING CAMERA …")
            else:
                self.video_widget.set_placeholder("WAITING FOR CAMERA")
            self.toasts.notify("Vision modules ready.", "success")

    @staticmethod
    def _show_module_errors(errors: dict[str, str]) -> None:
        """Aggregated WHAT/WHY/HOW TO FIX dialog for failed modules."""
        what = (
            f"{len(errors)} vision module(s) could not be initialized: "
            + ", ".join(sorted(errors))
        )
        why = (
            "Model files are missing or could not be loaded. "
            "(First start needs an internet connection once.)"
        )
        fix = (
            "Run: python scripts/download_models.py — then restart "
            "the app. The demo and analysis stay available without "
            "these modules."
        )
        details = "\n".join(f"{key}: {message}" for key, message in errors.items())
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("MODEL SETUP REQUIRED")
        box.setText(what)
        box.setInformativeText(f"WHY: {why}\n\nHOW TO FIX: {fix}")
        box.setDetailedText(details)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # ------------------------------------------------------------------
    # Errors / shutdown
    # ------------------------------------------------------------------
    @staticmethod
    def _show_error(title: str, message: str) -> None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._closing = True
        self._save_window_state()
        self._frame_timer.stop()
        self._stats_timer.stop()
        stage = getattr(self, "_stage_window", None)
        if stage is not None:
            stage.close()
        # Close-during-demo: abort the runner so it exits at the next
        # poll instead of running step timeouts to completion.
        runner = getattr(self, "_demo_runner", None)
        if runner is not None and not runner.completed:
            runner.abort()
        self.toasts.close_toasts()
        try:
            self.controller.stop_recording("window-closed")
        except Exception:  # noqa: BLE001 — teardown must not crash
            pass
        self.controller.shutdown()
        try:
            self.analysis_engine.close()
        except Exception:  # noqa: BLE001 — teardown must not crash
            pass
        self.image_engine.close()
        log.info("Main window closed")
        super().closeEvent(event)
