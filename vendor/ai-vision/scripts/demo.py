"""Reproducible demo runner — executes the complete product loop.

Runs the real application (offscreen) against the simulated demo camera:

    app start -> live vision -> objects/person/body/arms -> scene
    -> AI query -> image generation -> analysis -> match result
    -> feedback -> regeneration (v2) -> compare -> gallery
    -> DEMO COMPLETE

Real MediaPipe models are used for vision and analysis; the AI and image
providers are the clearly-labeled mock providers (no network/hardware
needed). Every frame is watermarked "DEMO FEED" — nothing is presented
as real hardware.

Usage:  python scripts/demo.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")



def main() -> int:
    from PySide6.QtWidgets import QApplication

    # Redirect all demo runtime data into a temp directory.
    data_dir = Path(tempfile.mkdtemp(prefix="ai-vision-lab-demo-"))
    os.environ["AI_VISION_LAB_DATA_DIR"] = str(data_dir)

    from app.config.settings import SettingsService
    from app.demo.frames import DemoCameraManager, DemoFrameSource
    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_theme
    from app.utils.logging_setup import setup_logging

    setup_logging(data_dir / "logs", debug=False)

    app = QApplication(sys.argv[:1])
    apply_theme(app, dark=True)

    settings_service = SettingsService(data_dir / "settings.json")
    settings_service.load()
    settings_service.update(
        llm_provider="mock",
        image_provider="mock",
        auto_analyze_generated=True,
        vision_mode="performance",
        camera_index=0,
        resolution="960x540",
    )

    window = MainWindow(
        settings_service,
        camera_manager=DemoCameraManager(),
        camera_capture_factory=DemoFrameSource,
        demo_mode=True,
    )
    window.resize(1560, 900)
    window.show()

    print("=== AI VISION LAB DEMO ===")
    print("simulated camera · real vision models · mock AI/image providers\n")

    steps = window.start_demo()
    summary = window._demo_runner.summary()
    print(summary)

    # Graceful shutdown: stop the demo camera and wait for the capture
    # thread before closing (avoids the MediaPipe teardown race).
    window.controller.stop_camera()
    import time as _time

    deadline = _time.monotonic() + 10.0
    while window.controller.is_running and _time.monotonic() < deadline:
        app.processEvents()
        _time.sleep(0.02)

    window.close()
    app.processEvents()

    passed = sum(1 for step in steps if step.status == "passed")
    print(f"\nRESULT: {passed}/{len(steps)} steps passed")
    return 0 if window._demo_runner.completed else 1


if __name__ == "__main__":
    sys.exit(main())
