"""Face mesh module (MediaPipe FaceLandmarker).

Produces 478 landmarks per face (468 canonical face mesh points + 10 iris
points) in pixel coordinates with the original z value. The bounding box
is derived from the landmarks themselves, so the mesh works independently
of the detection module.
"""

from __future__ import annotations

import numpy as np

from app.core.errors import ModelLoadError, VisionError
from app.core.types import FaceBox, MeshFace, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.face._mediapipe_helpers import (
    MonotonicTimestamps,
    create_task_with_fallback,
    make_mp_image,
)
from app.vision.model_manager import ModelManager

log = get_logger("vision.face.mesh")

#: Landmarks used for the bounding box (excludes the 10 iris points so the
#: face box is not distorted by looking sideways).
_IRIS_INDICES = frozenset(range(468, 478))


class FaceMeshModule(VisionModule):
    """MediaPipe FaceLandmarker: 478 facial landmarks per face.

    Args:
        models_dir: Directory holding the model file (downloaded on demand).
        max_faces: Maximum number of faces tracked per frame.
        enabled: Initial enabled state (toggled in the GUI).
    """

    key = "face_mesh"
    display_name = "Face Mesh"

    def __init__(self, models_dir, max_faces: int = 4, enabled: bool = True,
                 use_gpu: bool = False) -> None:
        super().__init__(enabled=enabled)
        self._models = ModelManager(models_dir)
        self._max_faces = max_faces
        self._use_gpu = use_gpu
        self._landmarker = None
        self._timestamps = MonotonicTimestamps()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load the FaceLandmarker model."""
        if self.status is ModuleStatus.READY and self._landmarker is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python  # noqa: PLC0415 — lazy
            from mediapipe.tasks.python import vision  # noqa: PLC0415 — lazy
        except ImportError as exc:
            raise ModelLoadError(
                "mediapipe is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = self._models.ensure_model("face_landmarker")

        def build_options(base):
            return vision.FaceLandmarkerOptions(
                base_options=base,
                running_mode=mp_python.vision.RunningMode.VIDEO,
                num_faces=self._max_faces,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )

        try:
            self._landmarker, delegate = create_task_with_fallback(
                build_options,
                vision.FaceLandmarker.create_from_options,
                model_path,
                use_gpu=self._use_gpu,
                module_name="face_mesh",
            )
        except Exception as exc:  # noqa: BLE001 — invalid/corrupt model etc.
            raise ModelLoadError(
                f"Face landmarker model could not be initialised: {exc}"
            ) from exc
        self.status = ModuleStatus.READY
        self.status_message = "" if delegate == "gpu" else f"delegate: {delegate}"
        log.info("Face mesh model loaded (max faces %d)", self._max_faces)

    def unload(self) -> None:
        landmarker, self._landmarker = self._landmarker, None
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarker = self._landmarker
        if landmarker is None:
            raise VisionError("FaceMeshModule.process called before load()")

        height, width = frame.shape[:2]
        mp_image = make_mp_image(frame)
        output = landmarker.detect_for_video(mp_image, self._timestamps.next())

        for landmarks in output.face_landmarks[: self._max_faces]:
            points = np.array(
                [[lm.x * width, lm.y * height, lm.z] for lm in landmarks],
                dtype=np.float32,
            )
            bbox = _bbox_from_landmarks(points, width, height)
            result.mesh_faces.append(MeshFace(landmarks=points, bbox=bbox))


def _bbox_from_landmarks(
    points: np.ndarray,
    width: int,
    height: int,
    padding_ratio: float = 0.05,
) -> FaceBox:
    """Bounding box from landmark positions (padded, clamped to frame)."""
    face_points = points[[i for i in range(len(points)) if i not in _IRIS_INDICES]]
    xs, ys = face_points[:, 0], face_points[:, 1]
    x_min, x_max = float(xs.min()), float(xs.max())
    y_min, y_max = float(ys.min()), float(ys.max())
    pad_x = (x_max - x_min) * padding_ratio
    pad_y = (y_max - y_min) * padding_ratio

    x = max(0, int(x_min - pad_x))
    y = max(0, int(y_min - pad_y))
    w = min(width - x, int(x_max - x_min + 2 * pad_x) + 1)
    h = min(height - y, int(y_max - y_min + 2 * pad_y) + 1)
    return FaceBox(x=x, y=y, width=max(1, w), height=max(1, h), source="mesh")
