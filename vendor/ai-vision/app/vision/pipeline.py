"""Central vision pipeline: frames in -> aggregated results out.

Flow::

    Camera -> Frame -> VisionPipeline -> [Face Detection] -> [Face Mesh]
                                        -> ID tracking + linking -> Results -> UI

The pipeline is a thin orchestrator. Analysis lives in independent
:class:`VisionModule` objects that can be enabled/disabled at runtime;
Phase 2 modules (eye tracking, hands, ...) simply register here.
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

import numpy as np

from app.core.types import MeshFace, TrackedFace, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import ModuleStatus, VisionModule
from app.vision.scene import build_scene_snapshot
from app.vision.tracker import FaceTracker

log = get_logger("vision.pipeline")

#: Max centroid distance (as a fraction of the frame diagonal) for
#: attaching mesh landmarks to a tracked face.
_MESH_LINK_RATIO = 0.30


class VisionPipeline:
    """Owns the vision modules and produces one VisionResult per frame.

    Args:
        modules: Initial modules (optional; can also be registered later).
        tracker: Face ID tracker (injectable for tests).
    """

    def __init__(
        self,
        modules: Sequence[VisionModule] = (),
        tracker: Optional[FaceTracker] = None,
    ) -> None:
        self._modules: dict[str, VisionModule] = {}
        self._tracker = tracker or FaceTracker()
        for module in modules:
            self.register(module)

    # ------------------------------------------------------------------
    # Module management
    # ------------------------------------------------------------------
    def register(self, module: VisionModule) -> None:
        """Add a module; replaces an existing module with the same key."""
        if not module.key:
            raise ValueError("Vision module must define a non-empty 'key'")
        self._modules[module.key] = module
        log.debug("Vision module registered: %s", module.key)

    def module(self, key: str) -> Optional[VisionModule]:
        return self._modules.get(key)

    def modules(self) -> list[VisionModule]:
        return list(self._modules.values())

    def set_enabled(self, key: str, enabled: bool) -> None:
        module = self._modules.get(key)
        if module is None:
            raise KeyError(f"Unknown vision module: {key!r}")
        module.enabled = enabled
        log.info("Vision module '%s' %s", key, "enabled" if enabled else "disabled")

    def enabled_module_keys(self) -> list[str]:
        return [m.key for m in self._modules.values() if m.enabled]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load_all(self) -> dict[str, str]:
        """Load every registered module; returns {key: error message}.

        A failing module is marked ERROR and skipped during processing —
        one broken model never blocks the remaining pipeline.
        """
        errors: dict[str, str] = {}
        for module in self._modules.values():
            try:
                module.load()
                module.status = ModuleStatus.READY
                log.info("Vision module '%s' loaded", module.key)
            except Exception as exc:  # noqa: BLE001 — per-module isolation
                message = str(exc) or exc.__class__.__name__
                module._fail(message)
                errors[module.key] = message
                log.error("Vision module '%s' failed to load: %s", module.key, exc)
        if not errors:
            log.info("All vision modules loaded successfully")
        return errors

    def close(self) -> None:
        """Release all modules and clear tracking state."""
        for module in self._modules.values():
            module.close()
        self._tracker.reset()
        log.info("Vision pipeline closed")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray) -> VisionResult:
        """Run all enabled modules on one BGR frame and finalise results."""
        result = VisionResult(frame=frame, timestamp=time.monotonic())
        t_start = time.perf_counter()

        for module in self._modules.values():
            if not module.enabled or not module.is_ready:
                continue
            try:
                module.process(frame, result)
            except Exception:  # noqa: BLE001 — one bad frame must not kill the loop
                log.exception(
                    "Vision module '%s' raised during processing", module.key
                )

        self._finalize(result)
        result.processing_ms = (time.perf_counter() - t_start) * 1000.0
        return result

    # ------------------------------------------------------------------
    # Tracking + linking
    # ------------------------------------------------------------------
    def _finalize(self, result: VisionResult) -> None:
        """Turn raw detections/meshes into ID-stable tracked faces, link
        persons to faces, and build the scene snapshot."""
        if result.frame is None or getattr(result.frame, "size", 0) == 0:
            result.scene = build_scene_snapshot(result)
            return
        height, width = result.frame.shape[:2]

        boxes = list(result.detections)
        if not boxes:
            # No detector output (detection module off) -> mesh drives tracking.
            boxes = [mesh.bbox for mesh in result.mesh_faces]

        tracked = self._tracker.update(boxes, width, height)
        self._link_meshes(tracked, result.mesh_faces, width, height)
        result.faces = tracked

        self._link_person_faces(result, width, height)
        result.scene = build_scene_snapshot(result)

    @staticmethod
    def _link_person_faces(
        result: VisionResult, width: int, height: int
    ) -> None:
        """Link each tracked person to the face inside its box (if any).

        Pure geometry (face centroid within the person bbox); greedy
        nearest match so a face belongs to at most one person.
        """
        links: dict[int, int] = {}
        used_faces: set[int] = set()
        for person in result.persons:
            best_face_id: Optional[int] = None
            best_distance = float("inf")
            for face in result.faces:
                if face.id in used_faces:
                    continue
                cx, cy = face.bbox.centroid()
                if not person.bbox.contains((cx, cy)):
                    continue
                px, py = person.bbox.centroid()
                distance = float(np.hypot(cx - px, cy - py))
                if distance < best_distance:
                    best_distance = distance
                    best_face_id = face.id
            if best_face_id is not None:
                links[person.id] = best_face_id
                used_faces.add(best_face_id)
                person.face_id = best_face_id
        result.person_face_links = links

    @staticmethod
    def _link_meshes(
        tracked: list[TrackedFace],
        meshes: Sequence[MeshFace],
        width: int,
        height: int,
    ) -> None:
        """Attach each tracked face the mesh whose centroid is closest."""
        if not meshes:
            return
        diagonal = float(np.hypot(width, height)) or 1.0
        max_distance = _MESH_LINK_RATIO * diagonal
        for face in tracked:
            fx, fy = face.bbox.centroid()
            best: Optional[MeshFace] = None
            best_distance = float("inf")
            for mesh in meshes:
                mx, my = mesh.bbox.centroid()
                distance = float(np.hypot(mx - fx, my - fy))
                if distance < best_distance:
                    best_distance = distance
                    best = mesh
            if best is not None and best_distance <= max_distance:
                face.landmarks = best.landmarks

    def descriptors(self) -> list[dict[str, str]]:
        """Lightweight module info for the UI (name, key, status)."""
        return [
            {
                "key": module.key,
                "name": module.display_name,
                "status": module.status.value,
                "message": module.status_message,
            }
            for module in self._modules.values()
        ]


def build_default_pipeline_with_models(
    models_dir: object,
    enabled_face_detection: bool = True,
    enabled_face_mesh: bool = True,
    min_confidence: float = 0.5,
    enabled_eye_tracking: bool = True,
    enabled_blink_detection: bool = True,
    enabled_head_pose: bool = True,
    enabled_gaze_estimation: bool = True,
    session: object = None,
    calibration_store: object = None,
    smoothing: str = "medium",
    enabled_object_detection: bool = True,
    enabled_object_tracking: bool = True,
    enabled_hand_tracking: bool = True,
    enabled_gesture_recognition: bool = True,
    enabled_person_tracking: bool = True,
    object_confidence: float = 0.5,
    max_objects: int = 20,
    max_hands: int = 2,
    gesture_confidence: float = 0.5,
    use_gpu: bool = False,
    vision_mode: str = "balanced",
    enabled_body_tracking: bool = True,
) -> VisionPipeline:
    """Default pipeline wired to the local model directory.

    Registration order matters: face modules produce the shared mesh;
    eye/blink/head modules consume it; gaze combines eyes + head pose;
    object detection runs independently; object tracking, hand tracking
    and person tracking build on the raw detection outputs — the heavy
    inference (face mesh, object detector, hand landmarker) runs exactly
    once per frame. ``vision_mode`` (quality/balanced/performance)
    controls the frame interval and input scale of the heavy object/hand
    models; ``use_gpu`` requests the MediaPipe GPU delegate with an
    automatic CPU fallback (stability first).
    """
    from app.config.settings import VISION_MODES
    from app.session.session import GazeSession
    from app.vision.blink import BlinkDetectorModule
    from app.vision.body import BodyPoseModule
    from app.vision.eye import EyeTrackingModule, GazeModule
    from app.vision.face import (  # noqa: PLC0415 — lazy import by design
        FaceDetectionModule,
        FaceMeshModule,
    )
    from app.vision.gestures import GestureRecognitionModule
    from app.vision.hands import HandTrackingModule
    from app.vision.head import HeadPoseModule
    from app.vision.objects import ObjectDetectionModule, ObjectTrackingModule
    from app.vision.persons import PersonTrackingModule

    mode = VISION_MODES.get(vision_mode, VISION_MODES["balanced"])

    return VisionPipeline(
        modules=[
            FaceDetectionModule(
                models_dir=models_dir,
                min_confidence=min_confidence,
                enabled=enabled_face_detection,
                use_gpu=use_gpu,
            ),
            FaceMeshModule(
                models_dir=models_dir,
                enabled=enabled_face_mesh,
                use_gpu=use_gpu,
            ),
            BodyPoseModule(
                models_dir=models_dir,
                enabled=enabled_body_tracking,
                use_gpu=use_gpu,
                frame_interval=mode["pose_interval"],
                input_scale=mode["pose_scale"],
            ),
            EyeTrackingModule(enabled=enabled_eye_tracking),
            BlinkDetectorModule(
                session=session or GazeSession(),
                enabled=enabled_blink_detection,
            ),
            HeadPoseModule(enabled=enabled_head_pose),
            GazeModule(
                enabled=enabled_gaze_estimation,
                smoothing=smoothing,
                calibration_store=calibration_store,
            ),
            ObjectDetectionModule(
                models_dir=models_dir,
                min_confidence=object_confidence,
                max_objects=max_objects,
                enabled=enabled_object_detection,
                use_gpu=use_gpu,
                frame_interval=mode["object_interval"],
                input_scale=mode["object_scale"],
            ),
            ObjectTrackingModule(enabled=enabled_object_tracking),
            HandTrackingModule(
                models_dir=models_dir,
                max_hands=max_hands,
                enabled=enabled_hand_tracking,
                use_gpu=use_gpu,
                frame_interval=mode["hand_interval"],
                input_scale=mode["hand_scale"],
            ),
            GestureRecognitionModule(
                enabled=enabled_gesture_recognition,
                confidence_threshold=gesture_confidence,
            ),
            PersonTrackingModule(enabled=enabled_person_tracking),
        ]
    )
