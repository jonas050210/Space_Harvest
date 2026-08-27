"""AI Vision Lab — application entry point.

Run ``python main.py`` (or ``python start.py`` for the guided launcher).
"""

from __future__ import annotations

import argparse
import os
import sys

# Import cv2 before Qt: avoids Qt plugin path conflicts between OpenCV's
# bundled Qt and PySide6 on Linux (harmless on Windows/macOS). Also limit
# OpenCV's internal thread pool so inference + capture don't oversubscribe
# the CPU.
import cv2  # noqa: E402  (must stay before the Qt imports)

cv2.setNumThreads(max(2, min(4, os.cpu_count() or 4)))

# MediaPipe 0.10.x + protobuf 5+: patch GetPrototype before any later
# mediapipe import (start.py also applies this; belt-and-suspenders).
from app.utils.protobuf_compat import apply_protobuf_compat  # noqa: E402

apply_protobuf_compat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Vision Lab")
    parser.add_argument(
        "--debug", action="store_true", help="enable debug logging"
    )
    parser.add_argument(
        "--camera", type=int, default=None, help="override camera index"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="start in DEMO MODE (simulated camera, scripted product run)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="run the system diagnostics and exit",
    )
    args = parser.parse_args(argv)

    from app.config.settings import SettingsService
    from app.utils.logging_setup import get_logger, setup_logging
    from app.utils.paths import PROJECT_ROOT, logs_dir, settings_path

    # Settings first: debug flag may come from the command line or the file.
    settings_service = SettingsService(settings_path())
    settings_service.load()
    debug = args.debug or bool(settings_service.get("debug_mode", False))

    setup_logging(logs_dir(), debug=debug)
    log = get_logger("main")

    if args.check:
        from app.diagnostics import run_diagnostics

        report = run_diagnostics()
        print(report.render())
        return 1 if report.failed else 0
    log.info("=" * 60)
    log.info("AI Vision Lab %s starting", _version())
    log.info("=" * 60)

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv[:1])
        app.setApplicationName("AI Vision Lab")
        app.setOrganizationName("AI Vision Lab")

        from app.ui.main_window import MainWindow
        from app.ui.theme import apply_theme

        apply_theme(app, dark=bool(settings_service.get("dark_theme", True)))

        # Application icon (local asset — no external resources).
        icon_path = PROJECT_ROOT / "assets" / "app_icon.png"
        if icon_path.exists():
            from PySide6.QtGui import QIcon

            app.setWindowIcon(QIcon(str(icon_path)))

        if args.camera is not None:
            settings_service.update(camera_index=args.camera)

        demo_kwargs = {}
        if args.demo:
            from app.demo.frames import DemoCameraManager, DemoFrameSource

            log.info("Starting in DEMO MODE (simulated camera)")
            # Demo providers: real vision models + clearly-labeled mock
            # AI/image providers — no network or hardware required.
            settings_service.update(
                llm_provider="mock",
                image_provider="mock",
                auto_analyze_generated=True,
                vision_mode="performance",
                camera_index=0,
                resolution="960x540",
            )
            demo_kwargs = dict(
                camera_manager=DemoCameraManager(),
                camera_capture_factory=DemoFrameSource,
                demo_mode=True,
            )

        # Startup UX: the window paints immediately (INITIALIZING state);
        # vision modules load right after the event loop starts — the
        # user always sees a defined state, never a frozen blank window.
        window = MainWindow(
            settings_service, defer_vision_load=True, **demo_kwargs
        )
        window.show()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.load_vision_modules_now)
        log.info("Main window shown — entering event loop")

        if args.demo:
            steps = window.start_demo()
            passed = sum(1 for s in steps if s.status == "passed")
            log.info(
                "Demo finished: %d/%d steps passed", passed, len(steps)
            )
            for step in steps:
                log.info(
                    "  [%s] %s%s",
                    step.status.upper(), step.label,
                    f" — {step.detail}" if step.detail else "",
                )

        exit_code = app.exec()
        log.info("Event loop ended (exit code %d)", exit_code)
        return exit_code
    except Exception:  # noqa: BLE001 — last-resort reporting
        log.exception("Fatal error — application terminated")
        try:
            QMessageBox.critical(
                None,
                "AI Vision Lab — Fatal error",
                "The application crashed unexpectedly.\n"
                "See logs/vision_lab.log for technical details.",
            )
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        log.info("Program ended")


def _version() -> str:
    try:
        from app import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
