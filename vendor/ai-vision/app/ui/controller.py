"""Bridge between the Qt UI and the camera/vision core.

The :class:`CameraController` owns the camera engine, the vision pipeline,
the gaze session and the FPS meter. Frames are captured and analysed in a
worker thread; the UI polls :meth:`latest` on a QTimer, so the event loop
is never blocked by capture or inference. Cross-thread events (state
changes, errors) travel via Qt signals (auto-queued to the GUI thread).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal

from app.camera.camera_engine import CameraEngine
from app.camera.camera_manager import CameraManager
from app.config.calibration import CalibrationProfile, CalibrationStore
from app.config.settings import SettingsService
from app.core.errors import CameraError
from app.core.types import FpsStats, VisionResult
from app.ai.events import SceneMonitor
from app.session.session import GazeSession
from app.ui.annotator import annotate_frame
from app.vision.heatmap import GazeHeatmap
from app.utils.fps import FPSMeter
from app.utils.logging_setup import get_logger
from app.capture.recorder import RecordingInfo, SessionRecorder
from app.utils.paths import data_dir, models_dir, recordings_dir
from app.vision.body.connections import POSE_CONNECTIONS
from app.vision.face.mesh_topology import FACEMESH_TESSELATION
from app.vision.hands.connections import HAND_CONNECTIONS
from app.vision.pipeline import VisionPipeline, build_default_pipeline_with_models

log = get_logger("ui.controller")

#: Module keys that mirror a persisted setting flag.
_MODULE_KEYS = (
    "face_detection",
    "face_mesh",
    "body_tracking",
    "eye_tracking",
    "blink_detection",
    "head_pose",
    "gaze_estimation",
    "object_detection",
    "object_tracking",
    "hand_tracking",
    "gesture_recognition",
    "person_tracking",
)

#: Settings that map to a runtime module configuration method.
_MODULE_CONFIGURATORS = {
    "object_confidence_threshold": ("object_detection", "set_confidence"),
    "max_objects": ("object_detection", "set_max_objects"),
    "max_hands": ("hand_tracking", "set_max_hands"),
    "gesture_confidence_threshold": ("gesture_recognition", "set_confidence_threshold"),
}


class CameraController(QObject):
    """Owns the capture pipeline and exposes it to the GUI."""

    state_changed = Signal(bool)          # True = camera running
    error_occurred = Signal(str)          # user-friendly error message
    module_states_changed = Signal()      # vision module toggles/status changed
    cameras_discovered = Signal(list)     # list[CameraInfo]
    resolutions_probed = Signal(int, list)  # camera index, list[(w, h)]
    calibration_changed = Signal()        # profile saved/reset
    scene_events = Signal(list)           # list[VisionEvent] (scene changes)

    def __init__(
        self,
        settings_service: SettingsService,
        pipeline: Optional[VisionPipeline] = None,
        camera_manager: Optional[CameraManager] = None,
        parent: Optional[QObject] = None,
        capture_factory=None,
    ) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._settings = settings_service.settings

        # Session data (RAM only) + calibration storage (local JSON).
        self._session = GazeSession()
        self._calibration_store = CalibrationStore(
            data_dir() / "calibration.json"
        )
        # Scene change detection -> vision events (AI layer consumes them).
        self._scene_monitor = SceneMonitor()
        self._scene_events: list = []  # recent events (bounded in the UI)
        # Analytics (Phase 26): gaze heatmap (RAM-only, bounded grid) +
        # session start time for duration metrics.
        self._heatmap = GazeHeatmap()
        self._heatmap_dirty = True
        self._heatmap_overlay_cache: object = None
        self._session_started_at: object = None

        self._camera_manager = camera_manager or CameraManager()
        # Worker-thread safety: helper threads (discovery/probe) must
        # never emit Qt signals after the controller was destroyed.
        # shutdown() sets the event and joins the threads.
        self._shutdown_event = threading.Event()
        self._helper_threads: list[threading.Thread] = []
        self._pipeline = pipeline or build_default_pipeline_with_models(
            models_dir=models_dir(),
            enabled_face_detection=self._settings.face_detection,
            enabled_face_mesh=self._settings.face_mesh,
            min_confidence=self._settings.min_detection_confidence,
            enabled_eye_tracking=self._settings.eye_tracking,
            enabled_blink_detection=self._settings.blink_detection,
            enabled_head_pose=self._settings.head_pose,
            enabled_gaze_estimation=self._settings.gaze_estimation,
            session=self._session,
            calibration_store=self._calibration_store,
            smoothing=self._settings.gaze_smoothing,
            enabled_object_detection=self._settings.object_detection,
            enabled_object_tracking=self._settings.object_tracking,
            enabled_hand_tracking=self._settings.hand_tracking,
            enabled_gesture_recognition=self._settings.gesture_recognition,
            enabled_person_tracking=self._settings.person_tracking,
            object_confidence=self._settings.object_confidence_threshold,
            max_objects=self._settings.max_objects,
            max_hands=self._settings.max_hands,
            gesture_confidence=self._settings.gesture_confidence_threshold,
            use_gpu=(self._settings.vision_delegate == "gpu"),
            vision_mode=self._settings.vision_mode,
            enabled_body_tracking=self._settings.body_tracking,
        )
        # Wire persisted module states into the pipeline (only for modules
        # the pipeline actually contains — an injected/test pipeline may
        # provide a different set).
        for key in _MODULE_KEYS:
            if self._pipeline.module(key) is not None:
                self._pipeline.set_enabled(key, bool(getattr(self._settings, key)))

        self._fps_meter = FPSMeter(window_seconds=1.0)
        self._latest_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_result: Optional[VisionResult] = None

        self._engine = CameraEngine(
            on_frame=self._on_frame,
            on_error=self._on_camera_error,
            capture_factory=capture_factory,
        )
        # Local session recorder (Phase 28) — frames never leave the machine.
        self._recorder = SessionRecorder(recordings_dir())
        self._last_raw_frame: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def pipeline(self) -> VisionPipeline:
        return self._pipeline

    @property
    def camera_manager(self) -> CameraManager:
        return self._camera_manager

    @property
    def session(self) -> GazeSession:
        return self._session

    @property
    def recorder(self) -> SessionRecorder:
        return self._recorder

    @property
    def calibration_store(self) -> CalibrationStore:
        return self._calibration_store

    # ------------------------------------------------------------------
    # Camera discovery
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """True while the capture thread is active."""
        return self._engine.is_running

    def actual_resolution(self) -> tuple[int, int]:
        return self._engine.actual_resolution

    def _start_helper(self, name: str, target) -> None:
        """Run a helper task in a daemon thread, tracked for shutdown.

        Helper threads must never emit signals after the controller (and
        its Qt signals) was deleted — shutdown() sets the event and
        joins, and every worker checks the event before emitting.
        """
        if self._shutdown_event.is_set():
            return

        def _guarded() -> None:
            try:
                target()
            finally:
                pass

        thread = threading.Thread(
            target=_guarded, name=name, daemon=True
        )
        self._helper_threads.append(thread)
        thread.start()

    def _alive(self) -> bool:
        """True while signals may still be emitted safely."""
        return not self._shutdown_event.is_set()

    def refresh_cameras_async(self) -> None:
        """Discover cameras in a worker thread (keeps the UI responsive)."""

        def _work() -> None:
            try:
                cameras = self._camera_manager.discover()
            except Exception as exc:  # noqa: BLE001 — discovery must not crash UI
                log.exception("Camera discovery failed")
                if self._alive():
                    self.error_occurred.emit(f"Camera discovery failed: {exc}")
                cameras = []
            if self._alive():
                self.cameras_discovered.emit(cameras)

        self._start_helper("camera-discovery", _work)

    def probe_resolutions_async(self, index: int) -> None:
        """Probe resolutions in a worker thread; emits resolutions_probed.

        The probe opens the device briefly — skipped while the camera is
        running so capture is never interrupted.
        """
        if self._engine.is_running:
            return

        def _work() -> None:
            try:
                resolutions = self._camera_manager.probe_resolutions(index)
            except Exception as exc:  # noqa: BLE001 — probe must not crash UI
                log.exception("Resolution probe failed for camera %d", index)
                if self._alive():
                    self.error_occurred.emit(f"Resolution probe failed: {exc}")
                resolutions = []
            if self._alive():
                self.resolutions_probed.emit(index, resolutions)

        self._start_helper("resolution-probe", _work)

    # ------------------------------------------------------------------
    # Camera lifecycle
    # ------------------------------------------------------------------
    def start_camera(self) -> None:
        """Open the configured camera and begin capture + analysis."""
        if self._engine.is_running:
            log.warning("start_camera called while already running — ignored")
            return
        settings = self._settings_service.settings
        try:
            width, height = CameraManager.parse_resolution(settings.resolution)
        except ValueError:
            width, height = 1280, 720
        try:
            self._engine.start(
                index=settings.camera_index,
                width=width,
                height=height,
                fps_target=settings.fps_target,
            )
        except CameraError as exc:
            log.error("Could not start camera %d: %s", settings.camera_index, exc)
            self.error_occurred.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — never let the UI crash
            log.exception("Unexpected error while starting camera")
            self.error_occurred.emit(f"Unexpected camera error: {exc}")
            return
        # Fresh session: clear gaze samples, blinks, smoothing state.
        self._session.reset()
        self._heatmap.clear()
        self._heatmap_dirty = True
        self._heatmap_overlay_cache = None
        self._session_started_at = time.monotonic()
        self._scene_monitor.reset()
        self._scene_events = []
        for key in ("blink_detection", "gaze_estimation", "object_tracking",
                    "hand_tracking", "body_tracking"):
            module = self._pipeline.module(key)
            if module is not None and hasattr(module, "reset"):
                module.reset()
        self.state_changed.emit(True)

    def stop_camera(self) -> None:
        """Stop capture and release the camera (idempotent)."""
        if not self._engine.is_running:
            return
        try:
            self._engine.stop()
        except Exception as exc:  # noqa: BLE001
            log.exception("Error while stopping camera")
            self.error_occurred.emit(f"Error while stopping camera: {exc}")
        self._fps_meter.reset()
        stopped = self._recorder.stop("camera-stopped")
        if stopped is not None:
            log.info("Recording auto-stopped because the camera stopped")
        with self._latest_lock:
            self._latest_frame = None
            self._latest_result = None
            self._last_raw_frame = None
        self.state_changed.emit(False)

    # ------------------------------------------------------------------
    # Vision modules / settings
    # ------------------------------------------------------------------
    def set_module_enabled(self, key: str, enabled: bool) -> None:
        self._pipeline.set_enabled(key, enabled)
        self._settings_service.update(**{key: enabled})
        self.module_states_changed.emit()

    def load_vision_modules(self) -> dict[str, str]:
        """Load all vision models; returns {key: error} for failures."""
        return self._pipeline.load_all()

    def update_settings(self, **values: object) -> None:
        self._settings_service.update(**values)
        if "gaze_smoothing" in values:
            self.set_gaze_smoothing(str(values["gaze_smoothing"]))
        if "vision_mode" in values:
            self.apply_vision_mode(str(values["vision_mode"]))
        for key, (module_key, method_name) in _MODULE_CONFIGURATORS.items():
            if key in values:
                module = self._pipeline.module(module_key)
                method = getattr(module, method_name, None)
                if callable(method):
                    method(values[key])
        self.module_states_changed.emit()

    def apply_vision_mode(self, mode: str) -> None:
        """Apply a vision performance mode to the heavy modules at runtime.

        The GPU delegate is *not* switched at runtime — it is applied at
        module load and a change requires a restart (documented).
        """
        from app.config.settings import VISION_MODES

        config = VISION_MODES.get(mode)
        if config is None:
            log.warning("Unknown vision mode %r — ignored", mode)
            return
        object_module = self._pipeline.module("object_detection")
        hand_module = self._pipeline.module("hand_tracking")
        pose_module = self._pipeline.module("body_tracking")
        for module, interval_key, scale_key in (
            (object_module, "object_interval", "object_scale"),
            (hand_module, "hand_interval", "hand_scale"),
            (pose_module, "pose_interval", "pose_scale"),
        ):
            if module is not None and hasattr(module, "set_performance_mode"):
                module.set_performance_mode(
                    int(config[interval_key]), float(config[scale_key])
                )
        log.info(
            "Vision mode '%s' applied (object every %d frame(s), hand every %d frame(s))",
            mode,
            config["object_interval"],
            config["hand_interval"],
        )

    def set_gaze_smoothing(self, strength: str) -> None:
        module = self._pipeline.module("gaze_estimation")
        if module is not None and hasattr(module, "set_smoothing"):
            module.set_smoothing(strength)

    def pipeline_descriptors(self) -> list[dict[str, str]]:
        return self._pipeline.descriptors()

    def delegate_summary(self) -> dict[str, str]:
        """Honest delegate status per loaded module (e.g. 'delegate: cpu').

        Only modules that actually report a delegate are included — the
        UI never shows a GPU status that was not reported by the module.
        """
        summary: dict[str, str] = {}
        for module in self._pipeline.modules():
            message = getattr(module, "status_message", "")
            if message:
                summary[module.key] = message
        return summary

    # ------------------------------------------------------------------
    # Gaze session + calibration
    # ------------------------------------------------------------------
    def session_stats(self) -> dict[str, object]:
        return self._session.blink_stats()

    # ---- Analytics (Phase 26) ----
    def recent_events(self, limit: int = 200) -> list:
        """Copy of the most recent scene events (bounded list)."""
        with self._latest_lock:
            return list(self._scene_events[-limit:])

    def heatmap_snapshot(self, width: int, height: int):
        """Current heatmap overlay (computed on demand, cached)."""
        if self._heatmap.sample_count == 0:
            return None
        if self._heatmap_dirty or self._heatmap_overlay_cache is None:
            self._heatmap_overlay_cache = self._heatmap.overlay(width, height)
            self._heatmap_dirty = False
        return self._heatmap_overlay_cache

    def analytics_state(self) -> dict[str, object]:
        """Everything the Insights page + recap need, in one cheap call."""
        from app.session.recap import summarize_events

        stats = self._session.blink_stats()
        events = self.recent_events()
        started = self._session_started_at
        duration = (
            round(time.monotonic() - started, 1)
            if isinstance(started, (int, float)) else 0.0
        )
        return {
            "duration_s": duration,
            "running": self.is_running,
            "blinks": stats,
            "gaze_samples": self._session.sample_count,
            "gaze_coverage": self._heatmap.coverage(),
            "events": events,
            "event_summary": summarize_events(events),
        }

    def calibration_status(self) -> Optional[dict[str, object]]:
        """Summary of the active calibration profile (None = no profile)."""
        profile = self._calibration_store.profile
        if profile is None:
            return None
        return {
            "quality": profile.quality,
            "valid_points": profile.valid_points,
            "total_points": profile.total_points,
            "screen": (profile.screen_width, profile.screen_height),
        }

    def save_calibration(self, profile: CalibrationProfile) -> None:
        """Persist a calibration profile and activate it immediately."""
        self._calibration_store.save(profile)
        module = self._pipeline.module("gaze_estimation")
        if module is not None and hasattr(module, "set_profile"):
            module.set_profile(profile)
        self.calibration_changed.emit()

    def reset_calibration(self) -> None:
        """Delete the profile; gaze falls back to the heuristic mapping."""
        self._calibration_store.reset()
        module = self._pipeline.module("gaze_estimation")
        if module is not None and hasattr(module, "set_profile"):
            module.set_profile(None)
        self.calibration_changed.emit()

    def latest_features(self) -> Optional[tuple[float, float, float, float]]:
        """Gaze features of the latest frame — calibration sampling input.

        Returns (iris_h, iris_v, yaw, pitch) or None when the face/iris
        data is unusable.
        """
        from app.vision.eye.gaze import gaze_features_from_result

        with self._latest_lock:
            result = self._latest_result
        if result is None:
            return None
        return gaze_features_from_result(result)

    # ------------------------------------------------------------------
    # Frame flow (worker thread) + UI polling
    # ------------------------------------------------------------------
    def _on_frame(self, frame: np.ndarray) -> None:
        result = self._pipeline.process(frame)

        # Scene change detection -> events for the AI layer.
        if result.scene is not None:
            try:
                events = self._scene_monitor.update(result.scene)
                if events:
                    self._scene_events.extend(events)
                    self._scene_events = self._scene_events[-200:]
                    self.scene_events.emit(list(events))
            except Exception:  # noqa: BLE001 — event layer must not break capture
                log.exception("Scene event detection failed")

        # Record the (smoothed) gaze point for trail/heatmap purposes.
        gaze = result.gaze
        if gaze is not None and gaze.valid and gaze.confidence > 0.0:
            self._session.add_sample(gaze.x, gaze.y, gaze.confidence)
            self._heatmap.add_points([(gaze.x, gaze.y, gaze.confidence)])
            self._heatmap_dirty = True

        settings = self._settings_service.settings
        heatmap_overlay = None
        if settings.show_gaze_heatmap and self._heatmap.sample_count > 0:
            if self._heatmap_dirty:
                self._heatmap_overlay_cache = self._heatmap.overlay(
                    frame.shape[1], frame.shape[0]
                )
                self._heatmap_dirty = False
            heatmap_overlay = self._heatmap_overlay_cache
        annotated = annotate_frame(
            frame,
            result,
            settings,
            FACEMESH_TESSELATION,
            heatmap_overlay=heatmap_overlay,
            gaze_trail=(
                self._session.recent_trail(settings.gaze_trail_length)
                if settings.gaze_trail
                else None
            ),
            hand_connections=HAND_CONNECTIONS,
            body_connections=POSE_CONNECTIONS,
        )
        if self._recorder.is_recording:
            self._recorder.write(annotated)
        with self._latest_lock:
            self._latest_frame = annotated
            self._latest_result = result
            self._last_raw_frame = frame
        self._fps_meter.tick()

    def _on_camera_error(self, exc: Exception) -> None:
        log.error("Camera failure: %s", exc)
        self.error_occurred.emit(str(exc))
        self.state_changed.emit(False)

    def start_recording(self, fps: Optional[float] = None):
        """Start a local video recording of the live camera frames."""
        if not self.is_running:
            raise RuntimeError("Start the camera before recording.")
        width, height = self.actual_resolution()
        if width < 16 or height < 16:
            with self._latest_lock:
                raw = self._last_raw_frame
            if raw is None:
                raise RuntimeError("No camera frame available to record.")
            height, width = raw.shape[:2]
        stats = self._fps_meter.stats
        used_fps = fps if fps and fps > 1 else (stats.fps or 15.0)
        return self._recorder.start(width, height, used_fps)

    def stop_recording(self, reason: str = "stopped") -> Optional[RecordingInfo]:
        return self._recorder.stop(reason)

    def take_snapshot(self) -> Path:
        """Save the latest raw camera frame as a JPEG (local only)."""
        with self._latest_lock:
            raw = self._last_raw_frame
            annotated = self._latest_frame
        frame = raw if raw is not None else annotated
        if frame is None:
            raise RuntimeError("No frame to snapshot — start the camera first.")
        return self._recorder.snapshot(frame)

    def latest(self) -> tuple[Optional[np.ndarray], Optional[VisionResult], FpsStats]:
        """Latest annotated frame, analysis result and fps stats."""
        with self._latest_lock:
            return self._latest_frame, self._latest_result, self._fps_meter.stats

    def reset_fps(self) -> None:
        self._fps_meter.reset()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Stop everything and release all resources.

        Also stops and joins helper threads (camera discovery, resolution
        probes) so no worker can emit signals into deleted objects during
        interpreter/window teardown.
        """
        self._shutdown_event.set()
        self.stop_camera()
        for thread in list(self._helper_threads):
            if thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=2.0)
        self._helper_threads.clear()
        self._pipeline.close()
        log.info("Controller shut down")
