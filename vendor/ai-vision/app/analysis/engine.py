"""Deterministic image analysis: quality metrics, content detection and
prompt matching.

The local analysis pipeline reuses the existing MediaPipe models on a
static image — the same detectors as the live camera, no new inference
models. Quality metrics (brightness, sharpness) are real OpenCV
computations. Prompt matching is a deterministic token comparison of the
prompt text against the *actually detected* classes. Where something
cannot be judged, the result says so ("unable to determine") instead of
inventing a value.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import numpy as np

from app.core.types import ImageAnalysisResult, PromptMatch, SceneSnapshot
from app.utils.logging_setup import get_logger
from app.vision.pipeline import VisionPipeline

log = get_logger("analysis")

#: Quality thresholds (empirical, documented — not calibrated metrics).
_LOW_LIGHT = 60.0          # mean gray value
_BLUR_SHARPNESS = 40.0     # variance of the Laplacian
_MIN_SIDE_RESOLUTION = 512

#: Classes that the EfficientDet COCO label set can name (used to find
#: prompt terms that are actually checkable).
_COCO_CLASSES: frozenset[str] = frozenset({
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
})


def image_quality_metrics(image_bgr: np.ndarray) -> tuple[dict, list[str]]:
    """Real brightness/sharpness metrics and derived issues. Never raises."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    height, width = image_bgr.shape[:2]

    metrics = {
        "brightness": round(brightness, 1),
        "sharpness": round(sharpness, 1),
        "resolution": f"{width}x{height}",
    }
    issues: list[str] = []
    if brightness < _LOW_LIGHT:
        issues.append("low light (image is dark)")
    if sharpness < _BLUR_SHARPNESS:
        issues.append("image appears blurry")
    if min(width, height) < _MIN_SIDE_RESOLUTION:
        issues.append("low resolution")
    return metrics, issues


def prompt_terms(prompt: str) -> list[str]:
    """COCO class terms mentioned in the prompt (lowercase matching)."""
    text = (prompt or "").lower()
    return sorted(
        {name for name in _COCO_CLASSES if f" {name} " in f" {text} "}
    )


def match_prompt(prompt: str, detected_classes: list[str]) -> PromptMatch:
    """Deterministic prompt-vs-detections comparison."""
    detected = set(detected_classes)
    wanted = set(prompt_terms(prompt))
    if not wanted:
        return PromptMatch(checked=False, extra=sorted(detected))
    matched = sorted(wanted & detected)
    missing = sorted(wanted - detected)
    extra = sorted(detected - wanted)
    score = len(matched) / len(wanted)
    if score >= 0.8:
        verdict = "good match"
    elif score >= 0.5:
        verdict = "partial match"
    else:
        verdict = "weak match"
    return PromptMatch(
        checked=True,
        matched=matched,
        missing=missing,
        extra=extra,
        score=round(score, 3),
        verdict=verdict,
    )


def build_analysis_pipeline(models_dir) -> VisionPipeline:
    """Pipeline for static-image analysis: content modules only.

    Eye/gaze/blink are deliberately excluded — they are temporal webcam
    features and meaningless for a single still image.
    """
    from app.vision.body import BodyPoseModule
    from app.vision.face import FaceDetectionModule, FaceMeshModule
    from app.vision.gestures import GestureRecognitionModule
    from app.vision.hands import HandTrackingModule
    from app.vision.objects import ObjectDetectionModule, ObjectTrackingModule
    from app.vision.persons import PersonTrackingModule

    return VisionPipeline(
        modules=[
            FaceDetectionModule(models_dir=models_dir, enabled=True),
            FaceMeshModule(models_dir=models_dir, enabled=True),
            BodyPoseModule(models_dir=models_dir, enabled=True),
            ObjectDetectionModule(models_dir=models_dir, enabled=True),
            ObjectTrackingModule(enabled=True),
            HandTrackingModule(models_dir=models_dir, enabled=True),
            GestureRecognitionModule(enabled=True),
            PersonTrackingModule(enabled=True),
        ]
    )


class ImageAnalysisEngine:
    """Runs local vision analysis on static images (uploaded/generated).

    Owns a *separate* pipeline instance (the live camera pipeline must
    never be shared with analysis jobs — it is stateful and runs in the
    capture thread). All analysis runs in worker threads.
    """

    def __init__(self, models_dir) -> None:
        self._models_dir = models_dir
        self._pipeline: Optional[VisionPipeline] = None
        self._lock = threading.Lock()          # load/close lifecycle
        self._process_lock = threading.Lock()  # serializes pipeline access
        self._load_errors: list[str] = []
        self._closed = False

    # ------------------------------------------------------------------
    @property
    def detectors_available(self) -> bool:
        return bool(self._pipeline) and not self._load_errors

    def ensure_loaded(self) -> None:
        """Load the analysis pipeline once (thread-safe)."""
        with self._lock:
            if self._closed:
                return
            if self._pipeline is not None:
                return
            pipeline = build_analysis_pipeline(self._models_dir)
            self._load_errors = list(pipeline.load_all().values())
            self._pipeline = pipeline
            if self._load_errors:
                log.warning(
                    "Analysis pipeline partially unavailable: %s",
                    self._load_errors,
                )

    def close(self) -> None:
        """Release the pipeline; waits for in-flight analyses.

        After close the engine refuses further analyses (final lifecycle).
        """
        # Wait for any in-flight analysis first — the pipeline must never
        # be torn down while a worker thread is inside process().
        with self._process_lock:
            with self._lock:
                self._closed = True
                if self._pipeline is not None:
                    self._pipeline.close()
                    self._pipeline = None
                    self._load_errors = []
        # MediaPipe releases native memory lazily; a collect here keeps
        # repeated engine lifecycles (tests, app restarts) flat.
        import gc

        gc.collect()

    # ------------------------------------------------------------------
    def analyze(
        self,
        image_bgr: np.ndarray,
        source: str = "uploaded",
        prompt: Optional[str] = None,
        snapshot: Optional[SceneSnapshot] = None,
    ) -> ImageAnalysisResult:
        """Blocking analysis — call from a worker thread. Never raises."""
        self.ensure_loaded()
        try:
            height, width = int(image_bgr.shape[0]), int(image_bgr.shape[1])
        except Exception:  # noqa: BLE001 — never raise out of analyze()
            return ImageAnalysisResult(
                source=source,
                issues=["invalid image"],
                timestamp=time.time(),
            )
        if (
            getattr(image_bgr, "ndim", 0) != 3
            or image_bgr.shape[2] < 3
            or height < 2
            or width < 2
        ):
            return ImageAnalysisResult(
                source=source,
                width=max(0, width),
                height=max(0, height),
                issues=["invalid image"],
                timestamp=time.time(),
            )
        try:
            quality, issues = image_quality_metrics(image_bgr)
        except Exception as exc:  # noqa: BLE001
            quality, issues = {}, [f"quality metrics failed: {exc}"]

        result = ImageAnalysisResult(
            source=source,
            width=width,
            height=height,
            quality=quality,
            issues=issues,
            detectors_available=bool(self._pipeline) and not self._load_errors,
            timestamp=time.time(),
        )

        try:
            # Serialize pipeline access: multiple auto-analyses may
            # overlap, and the pipeline (MediaPipe tasks) is stateful.
            with self._process_lock:
                if self._pipeline is None:
                    return result  # closed while waiting for the lock
                vision = self._pipeline.process(image_bgr)
        except Exception as exc:  # noqa: BLE001 — analysis must not crash
            log.exception("Image analysis pipeline failed")
            result.issues.append(f"analysis pipeline error: {exc}")
            return result

        result.objects = sorted({o.class_name for o in vision.objects})
        result.faces = len(vision.faces)
        result.hands = len(vision.hands)
        result.persons = len(vision.persons)
        result.gestures = sorted({g.gesture for g in vision.gestures})
        if vision.body is not None and vision.body.present:
            result.pose_present = True
            result.arm_states = dict(vision.body.arm_states)

        if prompt:
            result.prompt_match = match_prompt(prompt, result.objects)
        if snapshot is not None:
            result.comparison = self._compare_with_snapshot(snapshot, result)
        result.confidence = self._overall_confidence(result)
        return result

    def analyze_async(
        self,
        image_bgr: np.ndarray,
        source: str = "uploaded",
        prompt: Optional[str] = None,
        snapshot: Optional[SceneSnapshot] = None,
        on_done=None,
        on_error=None,
    ) -> threading.Thread:
        """Non-blocking analysis; callbacks run in the worker thread."""

        def _work() -> None:
            try:
                result = self.analyze(image_bgr, source, prompt, snapshot)
                if on_done is not None:
                    on_done(result)
            except Exception as exc:  # noqa: BLE001 — readable UI error
                log.exception("Image analysis failed")
                if on_error is not None:
                    on_error(str(exc))

        thread = threading.Thread(target=_work, name="image-analysis", daemon=True)
        thread.start()
        return thread

    # ------------------------------------------------------------------
    @staticmethod
    def _compare_with_snapshot(
        snapshot: SceneSnapshot, analysis: ImageAnalysisResult
    ) -> dict:
        """Deterministic comparison of the scene that prompted a generation
        with the content actually detected in the generated image."""
        comparison: dict = {"checkable": True}

        wanted_objects = sorted(set(snapshot.objects))
        if wanted_objects:
            detected = set(analysis.objects)
            comparison["objects_matched"] = sorted(detected & set(wanted_objects))
            comparison["objects_missing"] = [
                name for name in wanted_objects if name not in detected
            ]
            comparison["objects_extra"] = sorted(detected - set(wanted_objects))
        else:
            comparison["checkable"] = False

        if snapshot.gestures:
            detected_gestures = set(analysis.gestures)
            comparison["gestures_matched"] = sorted(
                detected_gestures & set(snapshot.gestures)
            )
            comparison["gestures_missing"] = sorted(
                set(snapshot.gestures) - detected_gestures
            )
        if snapshot.body_present:
            comparison["pose_present_in_image"] = analysis.pose_present
            if snapshot.arm_states:
                comparison["arm_states_in_scene"] = dict(snapshot.arm_states)
                comparison["arm_states_in_image"] = dict(analysis.arm_states)
        return comparison

    @staticmethod
    def _overall_confidence(result: ImageAnalysisResult) -> float:
        """Documented heuristic 0..1:
        0.4 content + 0.2 quality + 0.4 prompt match (neutral when
        uncheckable). Not a statistical probability.
        """
        content = 0.0
        if result.detectors_available:
            content = 1.0 if (
                result.objects or result.faces or result.hands
                or result.persons or result.pose_present
            ) else 0.2

        quality_score = 1.0
        if "low light (image is dark)" in result.issues:
            quality_score -= 0.3
        if "image appears blurry" in result.issues:
            quality_score -= 0.3
        quality_score = max(0.0, quality_score)

        if result.prompt_match.checked and result.prompt_match.score is not None:
            match_score = result.prompt_match.score
        else:
            match_score = 0.5  # neutral: nothing to check against

        return round(
            max(0.0, min(1.0, 0.4 * content + 0.2 * quality_score + 0.4 * match_score)),
            3,
        )
