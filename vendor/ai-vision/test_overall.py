"""Overall smoke test: the important components import and initialise.

Run with:  pytest test_overall.py   (or simply: pytest)

This is the acceptance test for Phase 1 wiring — it constructs the real
objects (with hardware replaced by stubs, as in the rest of the suite).
"""

from __future__ import annotations

import os

# Qt must run headless in CI/without display; set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from app import __version__
from app.camera.camera_engine import CameraEngine
from app.camera.camera_manager import CameraManager
from app.config.settings import SettingsService
from app.core.types import FaceBox, TrackedFace, VisionResult
from app.ui.annotator import annotate_frame
from app.ui.theme import apply_theme
from app.utils.fps import FPSMeter
from app.utils.logging_setup import get_logger, setup_logging
from app.utils.paths import data_dir, logs_dir, models_dir, settings_path
from app.vision.base import VisionModule
from app.vision.face.mesh_topology import FACEMESH_TESSELATION
from app.vision.pipeline import VisionPipeline
from app.vision.tracker import FaceTracker


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    apply_theme(app, dark=True)
    yield app


# ---------------------------------------------------------------------------
# Imports + version
# ---------------------------------------------------------------------------
def test_version_is_semver():
    assert __version__.count(".") == 2


def test_core_packages_importable():
    import importlib

    for package in (
        "app.camera",
        "app.config",
        "app.core",
        "app.ui",
        "app.utils",
        "app.vision",
        "app.vision.face",
    ):
        module = importlib.import_module(package)
        assert module.__name__ == package


def test_mesh_topology_is_valid():
    assert len(FACEMESH_TESSELATION) > 1000
    for a, b in FACEMESH_TESSELATION:
        assert 0 <= a < 468 and 0 <= b < 468


# ---------------------------------------------------------------------------
# Construction without hardware
# ---------------------------------------------------------------------------
def test_camera_engine_constructs():
    engine = CameraEngine(on_frame=lambda f: None, on_error=lambda e: None)
    assert not engine.is_running
    assert engine.index is None


def test_camera_manager_constructs():
    manager = CameraManager()
    assert manager.parse_resolution("1280x720") == (1280, 720)
    assert manager.resolution_label((1280, 720)) == "1280 × 720"


def test_fps_meter_initialises():
    meter = FPSMeter()
    stats = meter.stats
    assert stats.fps == 0.0
    assert stats.total_frames == 0


def test_face_tracker_constructs():
    tracker = FaceTracker()
    tracked = tracker.update([], 640, 480)
    assert tracked == []


def test_settings_service_initialises(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    settings = service.load()
    assert settings.resolution == "1280x720"
    assert settings.face_detection is True
    service.save()
    assert (tmp_path / "settings.json").exists()


def test_logging_setup_writes_log(tmp_path):
    setup_logging(tmp_path, debug=True)
    log = get_logger("test_overall")
    log.info("overall smoke test log entry")
    for handler in log.handlers:
        handler.flush()
    log_file = tmp_path / "vision_lab.log"
    assert log_file.exists()
    assert "overall smoke test log entry" in log_file.read_text(encoding="utf-8")


def test_project_directories_resolve_inside_project(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_VISION_LAB_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    assert logs_dir() == tmp_path / "logs"
    assert models_dir() == tmp_path / "models"
    assert settings_path() == tmp_path / "settings.json"


# ---------------------------------------------------------------------------
# Vision pipeline (stubs replace the MediaPipe modules)
# ---------------------------------------------------------------------------
class _StubDetection(VisionModule):
    key = "face_detection"
    display_name = "Face Detection"

    def load(self) -> None: ...

    def process(self, frame, result: VisionResult) -> None:
        result.detections.append(
            FaceBox(x=50, y=50, width=100, height=100, confidence=0.96, source="detector")
        )


def test_pipeline_processes_with_stub_module():
    stub = _StubDetection()
    pipeline = VisionPipeline(modules=[stub])
    assert pipeline.load_all() == {}
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    result = pipeline.process(frame)
    assert len(result.faces) == 1
    assert result.faces[0].id == 1
    assert result.faces[0].bbox.confidence == pytest.approx(0.96)
    assert result.processing_ms >= 0.0
    pipeline.close()


def test_annotator_draws_without_error():
    from app.config.settings import Settings

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    result = VisionResult(frame=frame)
    result.faces.append(
        TrackedFace(
            id=1,
            bbox=FaceBox(x=40, y=40, width=80, height=80, confidence=0.9, source="detector"),
        )
    )
    out = annotate_frame(frame, result, Settings(), connections=None)
    assert out.shape == frame.shape
    assert np.any(out != 0)  # box + label actually drawn


# ---------------------------------------------------------------------------
# GUI construction (headless)
# ---------------------------------------------------------------------------
def test_main_window_constructs_offscreen(qt_app, tmp_path, monkeypatch):
    from app.ui.main_window import MainWindow

    monkeypatch.setenv("AI_VISION_LAB_DATA_DIR", str(tmp_path))
    service = SettingsService(settings_path())
    service.load()
    window = MainWindow(service)
    assert window.windowTitle().startswith("AI Vision Lab")
    assert window.camera_panel is not None
    assert window.analysis_panel is not None
    assert window.video_widget is not None
    window.close()
    qt_app.processEvents()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
