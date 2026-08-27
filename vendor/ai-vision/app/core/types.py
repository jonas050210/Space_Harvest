"""Shared data structures exchanged between camera, vision and UI layers.

All coordinates are in *pixel* space of the processed frame, except where
explicitly documented. Vision modules and the UI both depend on these
types so the pipeline stays independent of Qt and OpenCV specifics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class Box:
    """Generic axis-aligned bounding box in pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    def centroid(self) -> tuple[float, float]:
        """Return (cx, cy) of the box centre."""
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    @property
    def area(self) -> int:
        return int(self.width) * int(self.height)

    def clamp_to(self, frame_width: int, frame_height: int) -> "Box":
        """Return a copy clamped to the frame bounds (defensive drawing)."""
        x = max(0, min(self.x, frame_width - 1))
        y = max(0, min(self.y, frame_height - 1))
        w = max(1, min(self.width, frame_width - x))
        h = max(1, min(self.height, frame_height - y))
        return Box(x, y, w, h)

    def contains(self, point: tuple[float, float]) -> bool:
        """True if the point lies inside the box."""
        px, py = point
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass
class FaceBox(Box):
    """Axis-aligned bounding box of a detected face (pixel coordinates)."""

    confidence: Optional[float] = None
    source: str = "unknown"  # e.g. "detector" or "mesh"

    def clamp_to(self, frame_width: int, frame_height: int) -> "FaceBox":
        """Return a copy clamped to the frame bounds (defensive drawing)."""
        x = max(0, min(self.x, frame_width - 1))
        y = max(0, min(self.y, frame_height - 1))
        w = max(1, min(self.width, frame_width - x))
        h = max(1, min(self.height, frame_height - y))
        return FaceBox(x, y, w, h, self.confidence, self.source)


@dataclass
class MeshFace:
    """Landmark mesh of one face: N x 3 array (x, y pixel, z) plus its bbox."""

    landmarks: np.ndarray
    bbox: FaceBox

    def __post_init__(self) -> None:
        arr = np.asarray(self.landmarks, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] < 2:
            raise ValueError(
                f"landmarks must be a 2D array of shape (N, >=2), got {arr.shape}"
            )
        self.landmarks = arr


@dataclass
class TrackedFace:
    """A face with a stable ID across frames, plus optional mesh landmarks."""

    id: int
    bbox: FaceBox
    landmarks: Optional[np.ndarray] = None  # (N, 3) x, y (px), z — may be None

    @property
    def landmark_count(self) -> int:
        return 0 if self.landmarks is None else int(self.landmarks.shape[0])

    @property
    def has_mesh(self) -> bool:
        return self.landmarks is not None and self.landmark_count > 0


@dataclass
class FpsStats:
    """Frame-rate measurement of one processing loop."""

    fps: float = 0.0
    frame_time_ms: float = 0.0
    total_frames: int = 0


@dataclass
class EyeData:
    """Per-eye analysis of one frame (subject perspective).

    ``side`` is ``"left"`` / ``"right"`` from the *person's* point of view
    (the person's left eye appears on the right side of the image).
    """

    side: str
    iris_center: Optional[tuple[float, float]] = None  # pixel coordinates
    iris_h: Optional[float] = None  # 0..1 across the eye box (0 = image left)
    iris_v: Optional[float] = None  # 0..1 down the eye box (0 = top)
    opening: Optional[float] = None  # eye aspect ratio (EAR)
    state: str = "lost"  # "tracked" | "closed" | "lost"
    eye_box: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h)


@dataclass
class HeadPose:
    """Head orientation in degrees (yaw/pitch/roll)."""

    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    valid: bool = False

    @property
    def max_angle(self) -> float:
        return max(abs(self.yaw), abs(self.pitch), abs(self.roll))


@dataclass
class BlinkFrameInfo:
    """Per-frame blink analysis plus session statistics snapshot."""

    state: str = "WAITING"  # WAITING | OPEN | CLOSING | CLOSED | OPENING
    ear: Optional[float] = None  # combined eye aspect ratio (mean of visible)
    ear_left: Optional[float] = None
    ear_right: Optional[float] = None
    count: int = 0  # blinks counted this session
    rate_per_min: float = 0.0  # blinks per minute (rolling 60 s window)
    last_blink_s: Optional[float] = None  # seconds since the last blink
    blink_event: bool = False  # a blink completed on this frame


@dataclass
class GazePoint:
    """Estimated gaze target in *normalized* video-area coordinates.

    ``x``/``y`` are 0..1 (0,0 = top-left of the camera image). The UI may
    scale them to the current resolution for display. This is an
    **estimate** from a normal webcam — explicitly not a medical or
    precision-grade measurement.
    """

    x: float = 0.5
    y: float = 0.5
    confidence: float = 0.0  # 0..1
    calibrated: bool = False  # True if a calibration profile was applied
    valid: bool = False

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.35


# ---------------------------------------------------------------------------
# Phase 3: objects, hands, gestures, persons, scene
# ---------------------------------------------------------------------------
@dataclass
class ObjectDetection:
    """Raw object detection of one frame (pre-tracking; id is 0 until the
    object tracker assigns a stable id)."""

    id: int = 0
    class_name: str = ""
    confidence: float = 0.0
    bbox: Box = field(default_factory=lambda: Box(0, 0, 1, 1))

    @property
    def center(self) -> tuple[float, float]:
        return self.bbox.centroid()


@dataclass
class TrackedObject:
    """A detected object with a stable id across frames."""

    id: int
    class_name: str
    confidence: float
    bbox: Box
    tracking_state: str = "tracked"  # "tracked" | "lost" (not reported)
    velocity: Optional[float] = None  # centroid shift in px/frame

    @property
    def center(self) -> tuple[float, float]:
        return self.bbox.centroid()

    @property
    def area(self) -> int:
        return self.bbox.area

    def relative_size(self, frame_width: int, frame_height: int) -> float:
        """Object area as a fraction of the frame area."""
        frame_area = max(1, frame_width * frame_height)
        return round(self.area / frame_area, 5)


@dataclass
class TrackedHand:
    """One tracked hand with 21 landmarks and handedness."""

    id: int
    handedness: str = ""  # "Left" | "Right" (person's perspective)
    handedness_confidence: float = 0.0
    landmarks: np.ndarray = field(default_factory=lambda: np.zeros((21, 3), np.float32))
    bbox: Box = field(default_factory=lambda: Box(0, 0, 1, 1))
    tracking_state: str = "tracked"
    finger_states: dict[str, str] = field(default_factory=dict)  # finger -> UP/DOWN

    def __post_init__(self) -> None:
        arr = np.asarray(self.landmarks, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[0] < 21:
            raise ValueError(
                f"hand landmarks must be (>=21, 3), got {arr.shape}"
            )
        self.landmarks = arr


@dataclass
class GestureResult:
    """Recognized gesture of one hand in one frame."""

    gesture: str  # e.g. "OPEN PALM", "FIST", "POINT", ... or "UNKNOWN"
    confidence: float  # 0..1 geometric plausibility
    hand_id: int
    handedness: str = ""
    timestamp: float = 0.0


@dataclass
class TrackedPerson:
    """A tracked person (derived from object detections of class 'person')."""

    id: int
    bbox: Box
    confidence: float = 0.0
    tracking_state: str = "tracked"
    face_id: Optional[int] = None  # linked face id (assigned by the pipeline)

    @property
    def center(self) -> tuple[float, float]:
        return self.bbox.centroid()


# ---------------------------------------------------------------------------
# Phase 6: body pose, image analysis, feedback
# ---------------------------------------------------------------------------
@dataclass
class BodyData:
    """Body pose of the first tracked person (33 MediaPipe pose landmarks).

    ``landmarks`` is (33, 3) x/y (px) + z; ``visibility`` is (33,) in 0..1.
    Arm states are geometric summaries: RAISED / OUT / NEUTRAL / DOWN /
    UNKNOWN (subject perspective).
    """

    landmarks: np.ndarray = field(
        default_factory=lambda: np.zeros((33, 3), np.float32)
    )
    visibility: np.ndarray = field(
        default_factory=lambda: np.zeros((33,), np.float32)
    )
    present: bool = False
    head_position: Optional[tuple[float, float]] = None
    shoulder_line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
    arm_states: dict[str, str] = field(default_factory=dict)  # left/right
    arm_angles: dict[str, Optional[float]] = field(default_factory=dict)
    shoulder_angle_deg: Optional[float] = None
    movement: Optional[tuple[float, float]] = None  # smoothed px/frame shift
    movement_speed: float = 0.0
    centroid: Optional[tuple[float, float]] = None

    def __post_init__(self) -> None:
        arr = np.asarray(self.landmarks, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[0] < 33:
            raise ValueError(f"body landmarks must be (>=33, 3), got {arr.shape}")
        self.landmarks = arr


@dataclass
class FeedbackEntry:
    """One user feedback about an image result."""

    rating: str  # "correct" | "wrong" | "partial"
    text: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rating": self.rating,
            "text": self.text,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Optional["FeedbackEntry"]:
        try:
            rating = str(raw.get("rating", ""))
            if rating not in {"correct", "wrong", "partial"}:
                return None
            return cls(
                rating=rating,
                text=str(raw.get("text", ""))[:2000],
                timestamp=float(raw.get("timestamp", 0.0)),
            )
        except (TypeError, ValueError):
            return None


@dataclass
class PromptMatch:
    """Deterministic comparison of a prompt against detected content."""

    checked: bool = False  # False = "unable to determine"
    matched: list[str] = field(default_factory=list)   # classes found
    missing: list[str] = field(default_factory=list)   # classes in prompt, not found
    extra: list[str] = field(default_factory=list)     # detected, not in prompt
    score: Optional[float] = None  # matched/(matched+missing), if checked
    verdict: str = "unable to determine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "matched": self.matched,
            "missing": self.missing,
            "extra": self.extra,
            "score": self.score,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PromptMatch":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            checked=bool(raw.get("checked", False)),
            matched=[str(x) for x in raw.get("matched", [])],
            missing=[str(x) for x in raw.get("missing", [])],
            extra=[str(x) for x in raw.get("extra", [])],
            score=(
                float(raw["score"]) if raw.get("score") is not None else None
            ),
            verdict=str(raw.get("verdict", "unable to determine")),
        )


@dataclass
class ImageAnalysisResult:
    """Structured analysis of one image (uploaded/generated/camera frame).

    All values come from real local detections/metrics. Where a property
    cannot be judged reliably, it is stated as "unable to determine" —
    never invented.
    """

    source: str = ""  # "uploaded" | "generated" | "camera"
    width: int = 0
    height: int = 0
    objects: list[str] = field(default_factory=list)
    faces: int = 0
    hands: int = 0
    persons: int = 0
    gestures: list[str] = field(default_factory=list)
    pose_present: bool = False
    arm_states: dict[str, str] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)  # real cv2 metrics
    issues: list[str] = field(default_factory=list)
    prompt_match: PromptMatch = field(default_factory=PromptMatch)
    comparison: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # heuristic 0..1, documented formula
    detectors_available: bool = False
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "objects": self.objects,
            "faces": self.faces,
            "hands": self.hands,
            "persons": self.persons,
            "gestures": self.gestures,
            "pose_present": self.pose_present,
            "arm_states": dict(self.arm_states),
            "quality": dict(self.quality),
            "issues": list(self.issues),
            "prompt_match": self.prompt_match.to_dict(),
            "comparison": dict(self.comparison),
            "confidence": self.confidence,
            "detectors_available": self.detectors_available,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ImageAnalysisResult":
        if not isinstance(raw, dict):
            return cls()
        quality = raw.get("quality")
        return cls(
            source=str(raw.get("source", "")),
            width=int(raw.get("width", 0)),
            height=int(raw.get("height", 0)),
            objects=[str(x) for x in raw.get("objects", [])],
            faces=int(raw.get("faces", 0)),
            hands=int(raw.get("hands", 0)),
            persons=int(raw.get("persons", 0)),
            gestures=[str(x) for x in raw.get("gestures", [])],
            pose_present=bool(raw.get("pose_present", False)),
            arm_states={
                str(k): str(v) for k, v in raw.get("arm_states", {}).items()
            },
            quality=quality if isinstance(quality, dict) else {},
            issues=[str(x) for x in raw.get("issues", [])],
            prompt_match=PromptMatch.from_dict(raw.get("prompt_match", {})),
            comparison=(
                raw.get("comparison")
                if isinstance(raw.get("comparison"), dict)
                else {}
            ),
            confidence=float(raw.get("confidence", 0.0)),
            detectors_available=bool(raw.get("detectors_available", False)),
            timestamp=float(raw.get("timestamp", 0.0)),
        )


@dataclass
class SceneSnapshot:
    """Structured summary of one frame — input for AI Vision (Phase 4).

    Built by the pipeline from the module results; contains no raw
    landmark or image data, only counts, names and scalar summaries.
    """

    faces: int = 0
    persons: int = 0
    objects: list[str] = field(default_factory=list)   # class names
    hands: int = 0
    gestures: list[str] = field(default_factory=list)  # gesture names
    gaze: Optional[tuple[float, float, float]] = None  # (x, y, confidence)
    head_pose: Optional[tuple[float, float, float]] = None  # (yaw, pitch, roll)
    # Phase 6: body pose summary (subject perspective arm states).
    body_present: bool = False
    arm_states: dict[str, str] = field(default_factory=dict)
    arm_angles: dict[str, Optional[float]] = field(default_factory=dict)
    shoulder_angle_deg: Optional[float] = None
    head_position: Optional[tuple[float, float]] = None  # normalized 0..1
    movement_speed: float = 0.0
    moving: bool = False


@dataclass
class VisionResult:
    """Aggregated output of one pipeline pass over a single frame.

    Modules write raw data into :attr:`detections` / :attr:`mesh_faces`;
    the pipeline then tracks faces across frames and fills :attr:`faces`
    with the final, ID-stable result consumed by the UI.
    """

    frame: Optional[np.ndarray] = None  # reference to the source frame (BGR)
    faces: list[TrackedFace] = field(default_factory=list)
    detections: list[FaceBox] = field(default_factory=list)   # raw detector output
    mesh_faces: list[MeshFace] = field(default_factory=list)  # raw mesh output

    # Phase 2: derived analysis, all based on the shared face mesh.
    eyes: list[EyeData] = field(default_factory=list)
    head_pose: Optional[HeadPose] = None
    blink: Optional[BlinkFrameInfo] = None
    gaze: Optional[GazePoint] = None

    # Phase 3: objects, hands, gestures, persons, scene.
    object_detections: list[ObjectDetection] = field(default_factory=list)  # raw
    objects: list[TrackedObject] = field(default_factory=list)              # tracked
    hands: list[TrackedHand] = field(default_factory=list)
    gestures: list[GestureResult] = field(default_factory=list)
    persons: list[TrackedPerson] = field(default_factory=list)
    person_face_links: dict[int, int] = field(default_factory=dict)  # person_id -> face_id
    scene: Optional[SceneSnapshot] = None

    # Phase 6: body pose.
    body: Optional[BodyData] = None

    processing_ms: float = 0.0
    timestamp: float = 0.0

    def bbox_diagonal(self) -> float:
        """Diagonal of the frame in pixels; used to normalise distances."""
        if self.frame is None:
            return 1.0
        h, w = self.frame.shape[:2]
        return float(math.hypot(w, h)) or 1.0

    def first_mesh(self) -> Optional[np.ndarray]:
        """Landmarks of the first tracked face with a mesh, if any."""
        for face in self.faces:
            if face.has_mesh:
                return face.landmarks
        return None

    def first_raw_mesh(self) -> Optional[np.ndarray]:
        """Landmarks for downstream modules (eye/blink/head/gaze).

        During a pipeline pass the raw ``mesh_faces`` are already
        populated while the tracked ``faces`` are only linked afterwards
        — downstream modules therefore read the raw mesh first. Falls back
        to tracked-face landmarks (e.g. for pre-linked test results).
        """
        for mesh in self.mesh_faces:
            return mesh.landmarks
        return self.first_mesh()
