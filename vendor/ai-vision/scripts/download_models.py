"""Download all five MediaPipe vision models (face, mesh, objects, hands, pose).

The app downloads models automatically on first use; run this script to
pre-download them (e.g. on a headless setup, behind a slow connection,
or to prepare an offline Windows build):

    python scripts/download_models.py

Models are stored in ``data/models/`` (~26 MB in total). For an offline
install, copy the ``data/models`` folder to the target machine — the
PyInstaller spec bundles it when present.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.logging_setup import get_logger, setup_logging  # noqa: E402
from app.utils.paths import logs_dir, models_dir  # noqa: E402
from app.vision.model_manager import ModelManager  # noqa: E402


def main() -> int:
    setup_logging(logs_dir(), debug=False)
    log = get_logger("download_models")
    log.info("Downloading vision models to %s", models_dir())

    manager = ModelManager(models_dir())

    def progress(downloaded: int, total: int) -> None:
        if total > 0:
            percent = downloaded / total * 100
            print(f"\r  {percent:5.1f} %  ({downloaded / 1e6:.2f} MB)", end="")

    try:
        paths = manager.download_all(progress=progress)
    except Exception as exc:  # noqa: BLE001 — readable CLI error
        print(f"\nFAILED: {exc}")
        return 1

    print("\nAll models available:")
    for name, path in paths.items():
        print(f"  - {name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
