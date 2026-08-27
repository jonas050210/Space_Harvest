"""Overlay presets for the live vision canvas.

A preset maps to concrete overlay settings (the same settings the
annotator already honors per frame). Selecting a preset applies real
setting changes — no fake toggles. CUSTOM means the user mixed them
manually.
"""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings

#: (preset key, label, settings dict)
OVERLAY_PRESETS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("minimal", "MINIMAL", {
        "show_landmark_points": False,
        "show_mesh_lines": False,
        "show_eye_overlay": False,
        "show_object_overlay": True,
        "show_hand_overlay": False,
        "show_body_skeleton": False,
        "show_body_joints": False,
        "movement_tracking": False,
        "gaze_cursor": False,
        "gaze_trail": False,
    }),
    ("body", "BODY", {
        "show_landmark_points": False,
        "show_mesh_lines": False,
        "show_eye_overlay": False,
        "show_object_overlay": False,
        "show_hand_overlay": True,
        "show_body_skeleton": True,
        "show_body_joints": True,
        "movement_tracking": True,
        "gaze_cursor": False,
        "gaze_trail": False,
    }),
    ("face", "FACE", {
        "show_landmark_points": True,
        "show_mesh_lines": False,
        "show_eye_overlay": True,
        "show_object_overlay": False,
        "show_hand_overlay": False,
        "show_body_skeleton": False,
        "show_body_joints": False,
        "movement_tracking": False,
        "gaze_cursor": True,
        "gaze_trail": True,
    }),
    ("objects", "OBJECTS", {
        "show_landmark_points": False,
        "show_mesh_lines": False,
        "show_eye_overlay": False,
        "show_object_overlay": True,
        "show_hand_overlay": False,
        "show_body_skeleton": False,
        "show_body_joints": False,
        "movement_tracking": True,   # movement arrow if a person moves
        "gaze_cursor": False,
        "gaze_trail": False,
    }),
    ("full", "FULL", {
        "show_landmark_points": True,
        "show_mesh_lines": False,
        "show_eye_overlay": True,
        "show_object_overlay": True,
        "show_hand_overlay": True,
        "show_body_skeleton": True,
        "show_body_joints": True,
        "movement_tracking": True,
        "gaze_cursor": True,
        "gaze_trail": True,
    }),
)

#: Labels for the individual overlay toggles (key -> label).
OVERLAY_TOGGLES: tuple[tuple[str, str], ...] = (
    ("show_gaze_heatmap", "Gaze Heatmap"),
    ("show_landmark_points", "Face Landmarks"),
    ("show_mesh_lines", "Mesh Lines"),
    ("show_eye_overlay", "Eye Overlay"),
    ("show_object_overlay", "Object Boxes"),
    ("show_hand_overlay", "Hand Skeleton"),
    ("show_body_skeleton", "Body Skeleton"),
    ("show_body_joints", "Body Joints"),
    ("movement_tracking", "Movement Arrow"),
    ("gaze_cursor", "Gaze Cursor"),
    ("gaze_trail", "Gaze Trail"),
)


def apply_overlay_preset(settings: Settings, preset_key: str) -> dict[str, Any]:
    """Return the settings updates for a preset (CUSTOM -> {})."""
    for key, _label, updates in OVERLAY_PRESETS:
        if key == preset_key:
            return dict(updates)
    return {}


def detect_preset(settings: Settings) -> str:
    """Which preset matches the current settings (or 'custom')."""
    for key, _label, updates in OVERLAY_PRESETS:
        if all(getattr(settings, name) == value
               for name, value in updates.items()):
            return key
    return "custom"
