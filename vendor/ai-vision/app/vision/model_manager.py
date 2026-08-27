"""Management of MediaPipe model files (.task / .tflite).

The models are not shipped inside the pip package; they live in the
project's ``data/models`` directory and are downloaded on first use
(``scripts/download_models.py`` does the same for headless setups).
Downloads are verified by size; the model itself is validated when the
MediaPipe task is created.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable, Optional

from app.core.errors import ModelLoadError
from app.utils.logging_setup import get_logger

log = get_logger("vision.models")

#: Model registry: key -> (file name, download URL, minimum file size).
MODEL_REGISTRY: dict[str, tuple[str, str, int]] = {
    "face_detector": (
        "blaze_face_short_range.tflite",
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        50_000,  # ~290 KB real file
    ),
    "face_landmarker": (
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task",
        1_000_000,  # ~3.7 MB real file
    ),
    # Phase 3
    "object_detector": (
        "efficientdet_lite0.tflite",
        "https://storage.googleapis.com/mediapipe-models/object_detector/"
        "efficientdet_lite0/float32/1/efficientdet_lite0.tflite",
        2_000_000,  # ~4.4 MB real file
    ),
    "hand_landmarker": (
        "hand_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task",
        3_000_000,  # ~7.4 MB real file
    ),
    # Phase 6
    "pose_landmarker": (
        "pose_landmarker_lite.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        2_500_000,  # ~5.5 MB real file
    ),
}


ProgressCallback = Callable[[int, int], None]


class ModelManager:
    """Locates, verifies and downloads vision model files."""

    def __init__(self, models_dir: Path) -> None:
        self._models_dir = Path(models_dir)
        try:
            self._models_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Creation happens on demand during download; a read-only or
            # restricted location must not break construction.
            pass

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    def model_path(self, name: str) -> Path:
        """Path where the model should live (independent of availability)."""
        if name not in MODEL_REGISTRY:
            raise KeyError(f"Unknown model: {name!r}")
        return self._models_dir / MODEL_REGISTRY[name][0]

    def is_available(self, name: str) -> bool:
        """True if a valid model file exists locally."""
        path = self.model_path(name)
        minimum = MODEL_REGISTRY[name][2]
        return path.is_file() and path.stat().st_size >= minimum

    def ensure_model(
        self,
        name: str,
        progress: Optional[ProgressCallback] = None,
    ) -> Path:
        """Return the local model path, downloading it first if needed.

        Raises:
            ModelLoadError: If the model is missing and cannot be downloaded.
        """
        if name not in MODEL_REGISTRY:
            raise KeyError(f"Unknown model: {name!r}")
        path = self.model_path(name)
        if self.is_available(name):
            log.debug("Model %s found at %s", name, path)
            return path

        filename, url, _ = MODEL_REGISTRY[name]
        log.info("Model %s missing — downloading from %s", name, url)
        try:
            self._download(url, path, progress)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            log.error("Download of %s failed: %s", name, exc)
            raise ModelLoadError(
                f"Could not download model '{name}' ({exc}). "
                "Check your internet connection or run "
                "`python scripts/download_models.py` manually."
            ) from exc

        if not self.is_available(name):
            raise ModelLoadError(
                f"Downloaded model '{name}' is too small or corrupt "
                f"({path}). Delete the file and retry."
            )
        log.info("Model %s downloaded to %s", name, path)
        return path

    def download_all(self, progress: Optional[ProgressCallback] = None) -> dict[str, Path]:
        """Ensure every registered model is available; returns paths."""
        return {
            name: self.ensure_model(name, progress) for name in MODEL_REGISTRY
        }

    @staticmethod
    def _download(
        url: str,
        destination: Path,
        progress: Optional[ProgressCallback],
    ) -> None:
        """Download with a progress callback (downloaded, total in bytes)."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_suffix(destination.suffix + ".part")
        tmp_path.unlink(missing_ok=True)

        def _reporter(blocks: int, block_size: int, total_size: int) -> None:
            if progress is not None:
                progress(blocks * block_size, total_size)

        try:
            urllib.request.urlretrieve(url, tmp_path, reporthook=_reporter)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        tmp_path.replace(destination)
