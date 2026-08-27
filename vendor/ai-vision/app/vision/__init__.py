"""Vision subsystem: module base, pipeline, face tracking, model manager.

Modules: face detection + mesh (``app.vision.face``), eye tracking and
gaze (``app.vision.eye``), blink detection (``app.vision.blink``), head
pose (``app.vision.head``), object detection + tracking
(``app.vision.objects``), hand tracking (``app.vision.hands``), gesture
recognition (``app.vision.gestures``) and person tracking
(``app.vision.persons``). Downstream modules reuse shared results — heavy
inference runs once per frame per model.
"""

from app.vision.base import ModuleStatus, VisionModule
from app.vision.model_manager import MODEL_REGISTRY, ModelManager
from app.vision.pipeline import (
    VisionPipeline,
    build_default_pipeline_with_models,
)
from app.vision.tracker import FaceTracker

__all__ = [
    "ModuleStatus",
    "VisionModule",
    "ModelManager",
    "MODEL_REGISTRY",
    "VisionPipeline",
    "build_default_pipeline_with_models",
    "FaceTracker",
]
