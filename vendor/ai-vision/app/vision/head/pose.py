"""Head pose estimation from shared face-mesh landmarks.

Uses OpenCV's ``solvePnP`` with a small generic 3-D face model anchored at
well-defined landmarks (nose tip, chin, eye corners, mouth corners). This
is the standard webcam approach: stable and cheap, but the angles are
*approximate* — the generic model does not match every face exactly, so
the values should be read as indicative (and are not medical-grade).
"""

from __future__ import annotations

import numpy as np

from app.core.types import HeadPose, VisionResult
from app.utils.logging_setup import get_logger
from app.vision.base import VisionModule

log = get_logger("vision.head.pose")

#: Landmark indices used for the pose fit.
_LANDMARK_IDS: tuple[int, ...] = (1, 152, 33, 263, 133, 362, 61, 291)

#: Approximate 3-D positions (mm) of those landmarks on a generic frontal
#: face in a right-handed camera frame: X right, Y **down** (matching
#: image coordinates), Z forward (nose towards the camera). This
#: orientation yields near-zero angles for frontal faces and avoids the
#: classic 180° flip that y-up generic models produce.
_MODEL_POINTS = np.asarray(
    [
        (0.0, 0.0, 0.0),         # 1    nose tip (origin)
        (0.0, 63.6, -12.5),      # 152  chin (below the nose)
        (-28.0, -28.0, -24.0),   # 33   right eye outer corner
        (28.0, -28.0, -24.0),    # 263  left eye outer corner
        (-8.0, -28.0, -24.0),    # 133  right eye inner corner
        (8.0, -28.0, -24.0),     # 362  left eye inner corner
        (-20.0, 20.0, -17.0),    # 61   mouth left corner
        (20.0, 20.0, -17.0),     # 291  mouth right corner
    ],
    dtype=np.float64,
)

#: Sanity bounds: pose angles beyond this are treated as invalid.
_MAX_ANGLE_DEG = 80.0


def estimate_head_pose(
    landmarks: np.ndarray,
    frame_width: int,
    frame_height: int,
) -> HeadPose:
    """Fit the head pose from one face's landmarks. Never raises.

    Args:
        landmarks: (N, >=2) landmark array in pixel coordinates.
        frame_width, frame_height: size of the frame (for the camera matrix).
    """
    try:
        import cv2  # noqa: PLC0415 — keep module import light
    except ImportError:
        return HeadPose(valid=False)

    if landmarks is None or len(landmarks) <= max(_LANDMARK_IDS):
        return HeadPose(valid=False)

    points = np.asarray(landmarks, dtype=np.float64)[list(_LANDMARK_IDS), :2]
    if not np.all(np.isfinite(points)):
        return HeadPose(valid=False)

    focal = float(max(frame_width, frame_height))
    camera_matrix = np.asarray(
        [[focal, 0.0, frame_width / 2.0],
         [0.0, focal, frame_height / 2.0],
         [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )

    try:
        ok, rvec, _tvec = cv2.solvePnP(
            _MODEL_POINTS,
            points,
            camera_matrix,
            None,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    except cv2.error:
        return HeadPose(valid=False)

    if not ok:
        return HeadPose(valid=False)

    rotation, _ = cv2.Rodrigues(rvec)
    yaw, pitch, roll = _rotation_to_euler(rotation)
    if max(abs(yaw), abs(pitch), abs(roll)) > _MAX_ANGLE_DEG:
        return HeadPose(valid=False)
    return HeadPose(
        yaw=round(float(yaw), 1),
        pitch=round(float(pitch), 1),
        roll=round(float(roll), 1),
        valid=True,
    )


def _rotation_to_euler(rotation: np.ndarray) -> tuple[float, float, float]:
    """Rotation matrix -> yaw/pitch/roll in degrees.

    Camera convention: X right, Y down, Z forward.

    * yaw   — rotation about the vertical Y axis (head turning left/right)
    * pitch — rotation about the horizontal X axis (head nodding)
    * roll  — rotation about the forward Z axis (head tilting)

    Standard extraction for R = Rx(pitch) * Ry(yaw) * Rz(roll); exact for
    single-axis rotations, a good approximation for moderate combined ones.

    Sign convention (pinned by the synthetic round-trip regression test
    in tests/test_phase13b_smoke.py — verify once on real hardware by
    turning your head and watching the LIVE INSPECTOR):

    * yaw   > 0  — face turned toward camera-RIGHT (subject's left)
    * pitch > 0  — nose pointing UP
    * roll  > 0  — top of the head tilted toward image-RIGHT
                  (subject's left shoulder)
    """
    yaw = np.arctan2(
        rotation[0, 2],
        np.sqrt(rotation[0, 0] ** 2 + rotation[0, 1] ** 2),
    )
    pitch = np.arctan2(-rotation[1, 2], rotation[2, 2])
    roll = np.arctan2(-rotation[0, 1], rotation[0, 0])
    return (
        float(np.degrees(yaw)),
        float(np.degrees(pitch)),
        float(np.degrees(roll)),
    )


class HeadPoseModule(VisionModule):
    """Vision module: head orientation of the first tracked face."""

    key = "head_pose"
    display_name = "Head Pose"

    def __init__(self, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)

    def load(self) -> None:
        self.status_message = ""

    def process(self, frame: np.ndarray, result: VisionResult) -> None:
        landmarks = result.first_raw_mesh()
        if landmarks is None:
            result.head_pose = None
            return
        height, width = frame.shape[:2]
        try:
            result.head_pose = estimate_head_pose(landmarks, width, height)
        except Exception:  # noqa: BLE001 — pipeline isolates failures
            log.exception("Head pose estimation failed on frame")
            result.head_pose = None
