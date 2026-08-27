"""Overlay drawing for the live camera view (pure OpenCV, no Qt).

Draws bounding boxes, face IDs, confidence, landmark mesh, eye tracking
overlay, gaze cursor, object boxes, hand skeletons, gesture labels and
person boxes onto a BGR frame. Runs in the worker thread so the GUI
thread only has to blit the finished image. Pure function of
(frame, result, settings, ...) — unit-testable without a display.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Sequence

import cv2
import numpy as np

from app.config.settings import Settings
from app.core.types import VisionResult

# BGR colours
_C_BOX = (0, 229, 255)        # cyan
_C_POINT = (124, 217, 43)     # green
_C_LINE = (66, 148, 168)      # dim cyan
_C_TEXT_BG = (10, 14, 19, 200)  # dark, semi-opaque
_C_TEXT = (216, 226, 234)
_C_EYE_BOX = (128, 148, 168)  # grey-blue eye boxes
_C_IRIS = (66, 205, 255)      # warm cyan iris
_C_GAZE = (0, 229, 255)       # cyan gaze cursor
_C_GAZE_RING = (255, 255, 255)
_C_TRAIL = (88, 138, 152)     # dim trail dots
_C_HAND_POINT = (255, 196, 66)  # amber hand points
_C_HAND_LINE = (168, 138, 88)   # dim amber hand lines
_C_PERSON = (0, 196, 255)     # orange-ish for persons
_C_BODY_LINE = (188, 66, 245)   # violet body skeleton
_C_BODY_JOINT = (245, 216, 120)  # pale amber joints
_C_MOVEMENT = (255, 255, 255)   # movement arrow

_LINE_ALPHA = 0.45


def _blend_heatmap(frame_bgr: np.ndarray, overlay: np.ndarray) -> None:
    """Blend an RGBA heatmap overlay onto the frame (in place).

    The overlay's alpha channel controls the mix; zero-alpha pixels
    leave the frame untouched.
    """
    bgr = overlay[:, :, :3].astype(np.float32)
    alpha = (overlay[:, :, 3].astype(np.float32) / 255.0)[..., None]
    blended = frame_bgr.astype(np.float32) * (1.0 - alpha) + bgr * alpha
    np.copyto(frame_bgr, np.clip(blended, 0, 255).astype(np.uint8))
_POINT_RADIUS = 1
_HAND_POINT_RADIUS = 2

#: Minimum confidence for drawing the gaze cursor.
_MIN_CURSOR_CONFIDENCE = 0.35


def annotate_frame(
    frame_bgr: np.ndarray,
    result: VisionResult,
    settings: Settings,
    connections: Optional[Sequence[tuple[int, int]]] = None,
    gaze_trail: Optional[Sequence[tuple[float, float]]] = None,
    hand_connections: Optional[Sequence[tuple[int, int]]] = None,
    body_connections: Optional[Sequence[tuple[int, int]]] = None,
    heatmap_overlay: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Draw overlays onto the frame (in place) and return it.

    Args:
        frame_bgr: BGR frame to draw on (mutated).
        result: Pipeline result of this frame.
        settings: Display-related settings.
        connections: Mesh line topology (index pairs); None disables lines.
        gaze_trail: Recent gaze points (normalized 0..1) for the trail.
        hand_connections: Hand skeleton topology (index pairs).
        body_connections: Body skeleton topology (index pairs).
        heatmap_overlay: RGBA gaze-heatmap overlay (Phase 26) — blended
            UNDER the boxes when settings.show_gaze_heatmap is enabled.
            None or mismatched size = no heatmap.
    """
    if (
        settings.show_gaze_heatmap
        and heatmap_overlay is not None
        and heatmap_overlay.ndim == 3
        and heatmap_overlay.shape[2] == 4
        and heatmap_overlay.shape[:2] == frame_bgr.shape[:2]
    ):
        _blend_heatmap(frame_bgr, heatmap_overlay)
    for face in result.faces:
        _draw_face(frame_bgr, face, settings, connections)

    if settings.show_body_skeleton or settings.show_body_joints:
        _draw_body(frame_bgr, result, settings, body_connections)

    if settings.show_eye_overlay:
        _draw_eye_overlay(frame_bgr, result)

    if settings.gaze_cursor:
        _draw_gaze_cursor(frame_bgr, result, settings, gaze_trail)

    if settings.show_object_overlay:
        _draw_objects(frame_bgr, result)
        _draw_persons(frame_bgr, result)

    if settings.show_hand_overlay:
        _draw_hands(frame_bgr, result, hand_connections)
    return frame_bgr


def _draw_face(
    frame: np.ndarray,
    face,
    settings: Settings,
    connections: Optional[Sequence[tuple[int, int]]],
) -> None:
    box = face.bbox.clamp_to(frame.shape[1], frame.shape[0])

    # Landmarks (below box/label so the mesh stays crisp).
    if face.has_mesh:
        points = np.asarray(face.landmarks, dtype=np.float32)
        if settings.show_mesh_lines and connections:
            _draw_mesh_lines(frame, points, connections)
        if settings.show_landmark_points:
            _draw_points(frame, points)

    # Bounding box + label.
    cv2.rectangle(frame, (box.x, box.y), (box.x + box.width, box.y + box.height), _C_BOX, 2)

    label = f"Face #{face.id}"
    if box.confidence is not None:
        label += f"  {box.confidence * 100:.0f}%"
    _draw_label(frame, label, box.x, max(0, box.y - 26))


def _draw_points(frame: np.ndarray, points: np.ndarray) -> None:
    int_points = points[:, :2].astype(np.int32)
    for x, y in int_points:
        cv2.circle(frame, (int(x), int(y)), _POINT_RADIUS, _C_POINT, -1, cv2.LINE_AA)


def _draw_mesh_lines(
    frame: np.ndarray,
    points: np.ndarray,
    connections: Sequence[tuple[int, int]],
) -> None:
    count = len(points)
    overlay = frame.copy()
    int_points = points[:, :2].astype(np.int32)
    for a, b in connections:
        if a < count and b < count:
            cv2.line(
                overlay,
                tuple(int_points[a]),
                tuple(int_points[b]),
                _C_LINE,
                1,
                cv2.LINE_AA,
            )
    cv2.addWeighted(overlay, _LINE_ALPHA, frame, 1.0 - _LINE_ALPHA, 0, frame)


def _draw_label(frame: np.ndarray, text: str, x: int, y: int) -> None:
    """Small filled label above the box (background improves readability)."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    box_top = max(0, y - th - baseline - 6)
    cv2.rectangle(
        frame,
        (x, box_top),
        (x + tw + 10, box_top + th + baseline + 6),
        _C_TEXT_BG[:3],
        -1,
    )
    cv2.putText(
        frame,
        text,
        (x + 5, box_top + th + baseline + 1),
        font,
        scale,
        _C_TEXT,
        thickness,
        cv2.LINE_AA,
    )


def _draw_label_left(frame: np.ndarray, text: str, x: int, y: int) -> None:
    """Label anchored at its *right* edge (avoids overlapping the box)."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.45
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    left = max(0, x - tw - 8)
    top = max(0, y - th - baseline - 4)
    cv2.rectangle(
        frame,
        (left, top),
        (left + tw + 8, top + th + baseline + 4),
        _C_TEXT_BG[:3],
        -1,
    )
    cv2.putText(
        frame,
        text,
        (left + 4, top + th + baseline),
        font,
        scale,
        _C_TEXT,
        thickness,
        cv2.LINE_AA,
    )


# ---------------------------------------------------------------------------
# Eye tracking overlay
# ---------------------------------------------------------------------------
def _draw_eye_overlay(frame: np.ndarray, result: VisionResult) -> None:
    """Iris markers, eye boxes and direction ticks for both eyes."""
    height, width = frame.shape[:2]
    for eye in result.eyes:
        if eye.eye_box is None:
            continue
        x, y, w, h = eye.eye_box
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        cv2.rectangle(frame, (x, y), (x + w, y + h), _C_EYE_BOX, 1)

        label = f"{eye.side.upper()} EYE"
        if eye.state == "tracked":
            label += " ●"
        elif eye.state == "closed":
            label += " ✕"
        _draw_label_left(frame, label, x - 4, y - 6)

        if eye.state != "tracked" or eye.iris_center is None:
            continue

        ix, iy = int(eye.iris_center[0]), int(eye.iris_center[1])
        radius = max(2, int(min(w, h) * 0.18))
        cv2.circle(frame, (ix, iy), radius, _C_IRIS, 1, cv2.LINE_AA)
        cv2.circle(frame, (ix, iy), 2, _C_IRIS, -1, cv2.LINE_AA)

        # Direction tick from the eye centre towards the iris.
        cx, cy = x + w // 2, y + h // 2
        cv2.line(frame, (cx, cy), (ix, iy), _C_EYE_BOX, 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Gaze cursor + trail
# ---------------------------------------------------------------------------
def _draw_gaze_cursor(
    frame: np.ndarray,
    result: VisionResult,
    settings: Settings,
    gaze_trail: Optional[Sequence[tuple[float, float]]],
) -> None:
    """Gaze cursor (only with usable confidence) and optional trail."""
    gaze = result.gaze
    if gaze is None or not gaze.valid:
        return

    height, width = frame.shape[:2]
    if settings.gaze_trail and gaze_trail:
        for tx, ty in gaze_trail[-settings.gaze_trail_length :]:
            px, py = int(tx * width), int(ty * height)
            if 0 <= px < width and 0 <= py < height:
                cv2.circle(frame, (px, py), 2, _C_TRAIL, -1, cv2.LINE_AA)

    if gaze.confidence < _MIN_CURSOR_CONFIDENCE:
        return  # low confidence: no cursor, panel shows LOW CONFIDENCE

    px, py = int(gaze.x * width), int(gaze.y * height)
    px = max(0, min(px, width - 1))
    py = max(0, min(py, height - 1))

    radius = max(3, settings.gaze_cursor_size)
    cv2.circle(frame, (px, py), radius, _C_GAZE_RING, 1, cv2.LINE_AA)
    cv2.circle(frame, (px, py), max(2, radius // 2), _C_GAZE, -1, cv2.LINE_AA)

    _draw_label(
        frame,
        f"GAZE {int(gaze.confidence * 100)}%",
        min(width - 150, px + radius + 6),
        max(20, py - radius - 6),
    )


# ---------------------------------------------------------------------------
# Body overlay (Phase 6)
# ---------------------------------------------------------------------------
def _draw_body(
    frame: np.ndarray,
    result: VisionResult,
    settings: Settings,
    connections: Optional[Sequence[tuple[int, int]]],
) -> None:
    body = result.body
    if body is None or not body.present:
        return
    height, width = frame.shape[:2]
    points = np.asarray(body.landmarks, dtype=np.float32)
    visibility = np.asarray(body.visibility, dtype=np.float32)
    int_points = points[:, :2].astype(np.int32)

    # Skeleton lines (visibility-dimmed).
    if settings.show_body_skeleton and connections:
        for a, b in connections:
            if a >= len(points) or b >= len(points):
                continue
            if visibility[a] < 0.4 or visibility[b] < 0.4:
                continue
            cv2.line(
                frame,
                tuple(int_points[a]),
                tuple(int_points[b]),
                _C_BODY_LINE,
                2,
                cv2.LINE_AA,
            )

    # Joints (size + alpha by visibility).
    if settings.show_body_joints:
        for index, (x, y) in enumerate(int_points):
            if visibility[index] < 0.4:
                continue
            radius = 3 if visibility[index] > 0.8 else 2
            cv2.circle(frame, (int(x), int(y)), radius, _C_BODY_JOINT, -1, cv2.LINE_AA)

    # Shoulder line emphasis.
    if body.shoulder_line is not None and settings.show_body_skeleton:
        (lx, ly), (rx, ry) = body.shoulder_line
        cv2.line(
            frame, (int(lx), int(ly)), (int(rx), int(ry)),
            _C_BODY_LINE, 2, cv2.LINE_AA,
        )

    # Movement arrow (smoothed velocity).
    if (
        settings.movement_tracking
        and body.movement is not None
        and body.centroid is not None
    ):
        speed = float(np.hypot(*body.movement))
        if speed > 1.0:
            cx, cy = body.centroid
            vx, vy = body.movement
            length = min(120.0, 30.0 + speed * 12.0)
            norm = float(np.hypot(vx, vy)) or 1.0
            ex = int(cx + vx / norm * length)
            ey = int(cy + vy / norm * length)
            if 0 <= ex < width and 0 <= ey < height:
                cv2.arrowedLine(
                    frame, (int(cx), int(cy)), (ex, ey),
                    _C_MOVEMENT, 2, cv2.LINE_AA, tipLength=0.25,
                )

    # Arm state labels next to the wrists.
    for side, wrist_id, elbow_id in (
        ("left", 15, 13), ("right", 16, 14),
    ):
        if wrist_id >= len(points):
            continue
        state = body.arm_states.get(side, "")
        if state and state != "UNKNOWN":
            wx, wy = int_points[wrist_id]
            if 0 <= wx < width and 0 <= wy < height:
                _draw_label_left(
                    frame, f"{side.upper()}: {state}", wx - 6, wy - 12
                )


# ---------------------------------------------------------------------------
# Object overlay
# ---------------------------------------------------------------------------
def class_color(class_name: str) -> tuple[int, int, int]:
    """Deterministic BGR colour per class name (stable across runs)."""
    digest = hashlib.md5(class_name.lower().encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") % 180
    bgr = cv2.cvtColor(
        np.uint8([[[hue, 210, 210]]]), cv2.COLOR_HSV2BGR
    )[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def _draw_objects(frame: np.ndarray, result: VisionResult) -> None:
    height, width = frame.shape[:2]
    for obj in result.objects:
        box = obj.bbox.clamp_to(width, height)
        color = class_color(obj.class_name)
        cv2.rectangle(frame, (box.x, box.y), (box.x + box.width, box.y + box.height), color, 2)

        label = f"{obj.class_name.upper()}  {obj.confidence * 100:.0f}%"
        _draw_label(frame, label, box.x, max(0, box.y - 24))
        _draw_label_left(frame, f"ID #{obj.id}", box.x - 4, box.y - 4)


def _draw_persons(frame: np.ndarray, result: VisionResult) -> None:
    """Person boxes (distinct colour) with the linked face id."""
    height, width = frame.shape[:2]
    face_links = result.person_face_links
    for person in result.persons:
        box = person.bbox.clamp_to(width, height)
        cv2.rectangle(
            frame,
            (box.x, box.y),
            (box.x + box.width, box.y + box.height),
            _C_PERSON,
            2,
        )
        label = f"PERSON #{person.id}"
        if person.id in face_links:
            label += f"  [Face #{face_links[person.id]}]"
        _draw_label(frame, label, box.x, max(0, box.y - 24))


# ---------------------------------------------------------------------------
# Hand overlay
# ---------------------------------------------------------------------------
def _draw_hands(
    frame: np.ndarray,
    result: VisionResult,
    connections: Optional[Sequence[tuple[int, int]]],
) -> None:
    height, width = frame.shape[:2]
    gestures = {g.hand_id: g for g in result.gestures}

    for hand in result.hands:
        points = np.asarray(hand.landmarks, dtype=np.float32)
        int_points = points[:, :2].astype(np.int32)

        # Skeleton lines.
        if connections:
            overlay = frame.copy()
            for a, b in connections:
                if a < len(points) and b < len(points):
                    cv2.line(
                        overlay,
                        tuple(int_points[a]),
                        tuple(int_points[b]),
                        _C_HAND_LINE,
                        1,
                        cv2.LINE_AA,
                    )
            cv2.addWeighted(overlay, _LINE_ALPHA, frame, 1.0 - _LINE_ALPHA, 0, frame)

        # Landmark points.
        for x, y in int_points:
            cv2.circle(frame, (int(x), int(y)), _HAND_POINT_RADIUS, _C_HAND_POINT, -1, cv2.LINE_AA)

        # Bounding box.
        box = hand.bbox.clamp_to(width, height)
        cv2.rectangle(
            frame, (box.x, box.y), (box.x + box.width, box.y + box.height), _C_HAND_LINE, 1
        )

        label = f"{hand.handedness.upper()} HAND" if hand.handedness else "HAND"
        if hand.handedness_confidence:
            label += f"  {hand.handedness_confidence * 100:.0f}%"
        _draw_label_left(frame, label, box.x - 4, box.y - 6)

        # Gesture label above the hand.
        gesture = gestures.get(hand.id)
        if gesture is not None:
            gesture_label = f"{gesture.gesture}  {gesture.confidence * 100:.0f}%"
            _draw_label(frame, gesture_label, box.x, max(0, box.y - 46))
