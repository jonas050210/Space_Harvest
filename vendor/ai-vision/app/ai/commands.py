"""Deterministic vision commands — answered from data, no LLM needed.

The seven built-in commands (WHAT DO I SEE?, DESCRIBE SCENE, LIST OBJECTS,
HOW MANY PEOPLE?, WHAT GESTURE?, WHERE AM I LOOKING?, VISION SUMMARY) are
answered directly from the SceneSnapshot. This is the most honest
implementation: the answers contain exactly what the vision pipeline
reported — nothing more. They work fully offline and never hallucinate.

Natural-language queries (English and German) that match one of the
commands are routed here as well; free-form questions go to the LLM.
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.types import SceneSnapshot

#: Canonical command buttons of the AI panel.
COMMANDS: tuple[str, ...] = (
    "WHAT DO I SEE?",
    "DESCRIBE SCENE",
    "LIST OBJECTS",
    "HOW MANY PEOPLE?",
    "WHAT GESTURE?",
    "WHERE AM I LOOKING?",
    "WHAT IS MOVING?",
    "ARM STATE?",
    "DESCRIBE PERSON",
    "VISION SUMMARY",
    "CREATE SCENE IMAGE",
)

#: Keyword groups per command (lowercase, matched as substrings).
_PATTERNS: dict[str, tuple[str, ...]] = {
    "WHAT DO I SEE?": (
        "what do i see", "was sehe ich", "was siehst du",
        "what do you see",
    ),
    "DESCRIBE SCENE": (
        "describe scene", "describe the scene", "beschreibe die szene",
        "beschreib die szene", "scene beschreibung",
    ),
    "LIST OBJECTS": (
        "list objects", "welche objekte", "objects on the table",
        "objekte auf dem tisch", "liste objekte",
    ),
    "HOW MANY PEOPLE?": (
        "how many people", "wie viele personen", "anzahl personen",
    ),
    "WHAT GESTURE?": (
        "what gesture", "welche geste", "geste mache",
    ),
    "WHERE AM I LOOKING?": (
        "where am i looking", "wohin schaue", "was schaue ich an",
        "where is the person looking", "was schaut die person",
    ),
    "SESSION RECAP": (
        "session recap", "recap the session", "was ist passiert",
        "was ist diese session passiert", "sitzung zusammenfassung",
        "zusammenfassung der sitzung", "summarize the session",
        "session summary",
    ),
    "VISION SUMMARY": (
        "vision summary", "zusammenfassung", "summary",
    ),
    "WHAT IS MOVING?": (
        "what is moving", "was bewegt sich", "bewegung",
        "is anything moving", "bewegt sich etwas",
    ),
    "DESCRIBE PERSON": (
        "describe person", "describe the person",
        "beschreibe die person", "beschreib die person",
        "person beschreibung", "wer ist die person",
        "what is the person doing", "was macht die person",
    ),
    "ARM STATE?": (
        "what is my left arm doing", "was macht mein linker arm",
        "linker arm", "left arm", "was macht mein rechter arm",
        "right arm", "rechter arm",
    ),
    "CAPTURE AND GENERATE": (
        "capture and generate", "capture & generate",
        "erfasse und generiere", "aufnehmen und generieren",
        "scene aufnehmen und generieren",
    ),
    "START RECORDING": (
        "start recording", "start the recording", "record this",
        "begin recording",
    ),
    "STOP RECORDING": (
        "stop recording", "stop the recording", "end recording",
    ),
    "TAKE SNAPSHOT": (
        "take a snapshot", "take snapshot", "save a snapshot",
        "save this frame", "capture a still",
    ),
    "CREATE SCENE IMAGE": (
        "create an image", "create a picture", "generate an image",
        "erstelle ein bild", "erzeuge ein bild", "mach ein bild",
        "bild von dem, was die kamera", "bild von der szene",
        "image of the scene", "picture of what the camera sees",
    ),
    "ANALYZE IMAGE": (
        "analyze this image", "analysiere dieses bild", "analysiere das bild",
        "analyze the image", "analyze the last image",
    ),
    "COMPARE IMAGES": (
        "compare the two images", "vergleiche die beiden bilder",
        "compare images", "vergleiche die bilder",
    ),
    "IMPROVE IMAGE": (
        "improve the last image", "verbessere das letzte bild",
        "improve the image", "verbessere das bild",
    ),
    "GENERATE VARIANT": (
        "generate a variant", "generiere eine variante", "variation",
        "erzeuge eine variante", "make a variation",
    ),
    "WHAT CHANGED?": (
        "what is different", "was ist anders", "what changed",
        "was hat sich geändert", "was hat sich veraendert",
    ),
}

_GAZE_QUADRANT_NAMES = {
    ("top", "left"): "the upper left area",
    ("top", "right"): "the upper right area",
    ("bottom", "left"): "the lower left area",
    ("bottom", "right"): "the lower right area",
}


def match_command(
    query: str,
    extra: Optional[dict[str, tuple[str, ...]]] = None,
) -> Optional[str]:
    """Return the canonical command matching the query, if any."""
    normalized = re.sub(r"[^a-z0-9 äöüß]+", " ", query.lower()).strip()
    for command, keywords in _PATTERNS.items():
        if any(keyword in normalized for keyword in keywords):
            return command
    if extra:
        for command, keywords in extra.items():
            if any(keyword in normalized for keyword in keywords):
                return command
    return None


def answer_command(command: str, snapshot: Optional[SceneSnapshot]) -> str:
    """Deterministic answer for a canonical command. Never raises."""
    if command == "LIST OBJECTS":
        return _list_objects(snapshot)
    if command == "HOW MANY PEOPLE?":
        return _how_many_people(snapshot)
    if command == "WHAT GESTURE?":
        return _what_gesture(snapshot)
    if command == "WHERE AM I LOOKING?":
        return _where_looking(snapshot)
    if command == "WHAT IS MOVING?":
        return _what_is_moving(snapshot)
    if command == "ARM STATE?":
        return _arm_state(snapshot)
    if command == "DESCRIBE PERSON":
        return _describe_person(snapshot)
    if command in ("WHAT DO I SEE?", "DESCRIBE SCENE"):
        return _describe(snapshot)
    if command == "VISION SUMMARY":
        return _summary(snapshot)
    if command == "CREATE SCENE IMAGE":
        # Handled by the image intent handler in the UI (it builds the
        # prompt from the snapshot and enqueues the generation). If it is
        # ever reached here (no handler wired), answer honestly.
        return (
            "Image generation from the scene is not available right now."
            if snapshot is None
            else "Preparing an image prompt from the current scene…"
        )
    # Image-analysis intents (ANALYZE IMAGE / COMPARE IMAGES /
    # IMPROVE IMAGE / GENERATE VARIANT / WHAT CHANGED? / CAPTURE AND
    # GENERATE) are routed to the UI's intent handler; without one,
    # answer honestly instead of pretending an action happened.
    if command in (
        "ANALYZE IMAGE", "COMPARE IMAGES", "IMPROVE IMAGE",
        "GENERATE VARIANT", "WHAT CHANGED?", "CAPTURE AND GENERATE",
        "SESSION RECAP", "START RECORDING", "STOP RECORDING",
        "TAKE SNAPSHOT",
    ):
        return (
            f"Command '{command}' needs the studio UI — run it inside "
            "the application."
        )
    return _describe(snapshot)


# ---------------------------------------------------------------------------
# Command implementations (strictly from snapshot data)
# ---------------------------------------------------------------------------
def _no_data() -> str:
    return (
        "No vision data available. Start the camera and make sure "
        "something is visible."
    )


def _list_objects(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if not snapshot.objects:
        return "No objects detected in the current scene."
    items = ", ".join(sorted(set(snapshot.objects)))
    return f"Detected objects: {items}."


def _how_many_people(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if snapshot.persons == 0:
        return (
            "No persons detected in the current scene."
            + (f" {snapshot.faces} face(s) detected." if snapshot.faces else "")
        )
    return (
        f"{snapshot.persons} person(s) detected"
        + (f", with {snapshot.faces} face(s)." if snapshot.faces else ".")
    )


def _what_gesture(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if not snapshot.gestures:
        return "No gesture detected."
    return "Detected gesture(s): " + ", ".join(
        sorted(set(snapshot.gestures))
    ) + "."


def _where_looking(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if snapshot.gaze is None:
        return "No gaze data available."
    x, y, confidence = snapshot.gaze
    quadrant = _GAZE_QUADRANT_NAMES[
        ("top" if y < 0.5 else "bottom", "left" if x < 0.5 else "right")
    ]
    return (
        f"Estimated gaze points towards {quadrant} of the camera view "
        f"(normalized x={x:.2f}, y={y:.2f}, confidence {confidence:.0%}). "
        "This is an estimate from a normal webcam, not a precise measurement."
    )


def _describe(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    parts: list[str] = []

    if snapshot.persons:
        parts.append(f"{snapshot.persons} person(s)")
    if snapshot.faces:
        parts.append(f"{snapshot.faces} face(s)")

    objects = sorted(set(snapshot.objects))
    if objects:
        joined = ", ".join(objects)
        parts.append(f"objects: {joined}")

    if snapshot.hands:
        parts.append(f"{snapshot.hands} hand(s)")

    if snapshot.gestures:
        parts.append("gesture(s): " + ", ".join(sorted(set(snapshot.gestures))))

    if not parts:
        return "The camera is running, but nothing is detected in the current scene."

    sentence = "In the current scene I detect " + "; ".join(parts) + "."

    extras: list[str] = []
    if snapshot.gaze is not None:
        _x, _y, confidence = snapshot.gaze
        extras.append(f"gaze confidence {confidence:.0%}")
    if snapshot.head_pose is not None:
        yaw, pitch, _roll = snapshot.head_pose
        extras.append(f"head pose yaw={yaw:+.0f}° pitch={pitch:+.0f}°")
    if extras:
        sentence += " " + ", ".join(extras) + " (approximate)."
    return sentence


def _describe_person(snapshot: Optional[SceneSnapshot]) -> str:
    """Structured, offline description of the tracked person.

    Every value comes from the SceneSnapshot — nothing is invented.
    Head-pose signs follow the documented convention (yaw > 0 = face
    toward camera-right, pitch > 0 = nose up).
    """
    if snapshot is None:
        return _no_data()
    if not snapshot.body_present and not snapshot.faces:
        return (
            "No person is currently tracked. Step in front of the "
            "camera and make sure you are well lit."
        )
    parts: list[str] = []
    if snapshot.body_present:
        parts.append("body tracked")
        arms = []
        for side in ("left", "right"):
            state = snapshot.arm_states.get(side, "UNKNOWN")
            angle = snapshot.arm_angles.get(side)
            if state == "UNKNOWN" and angle is None:
                arms.append(f"{side} unknown")
            elif angle is not None:
                arms.append(f"{side} {state} at {angle:.0f}°")
            else:
                arms.append(f"{side} {state}")
        parts.append("arms: " + " · ".join(arms))
        if snapshot.shoulder_angle_deg is not None:
            parts.append(
                f"shoulder tilt {snapshot.shoulder_angle_deg:+.1f}°"
            )
    if snapshot.head_pose is not None:
        yaw, pitch, roll = snapshot.head_pose
        direction = _head_direction_text(yaw, pitch)
        parts.append(
            f"head: yaw {yaw:+.0f}° pitch {pitch:+.0f}° roll {roll:+.0f}° "
            f"({direction})"
        )
    if snapshot.gaze is not None:
        x, y, confidence = snapshot.gaze
        quadrant = _GAZE_QUADRANT_NAMES[
            ("top" if y < 0.5 else "bottom",
             "left" if x < 0.5 else "right")
        ]
        parts.append(
            f"gaze towards {quadrant} (confidence {confidence:.0%})"
        )
    if snapshot.body_present:
        if snapshot.moving and snapshot.movement_speed > 0:
            parts.append(f"moving at {snapshot.movement_speed:.1f} px/frame")
        else:
            parts.append("standing still")
    if snapshot.hands:
        parts.append(f"{snapshot.hands} hand(s) visible")
    if snapshot.gestures:
        parts.append("gesture: " + ", ".join(sorted(set(snapshot.gestures))))
    if not parts:
        return "The person is tracked, but no detail data is available yet."
    return "Tracked person — " + "; ".join(parts) + "."


def _head_direction_text(yaw: float, pitch: float) -> str:
    """Human-readable head orientation from the documented signs."""
    horizontal = "facing camera" if abs(yaw) < 10 else (
        "turned to camera-right" if yaw > 0 else "turned to camera-left"
    )
    vertical = "level" if abs(pitch) < 10 else (
        "looking up" if pitch > 0 else "looking down"
    )
    if horizontal == "facing camera" and vertical == "level":
        return "facing the camera, level"
    return f"{horizontal}, {vertical}"


def _what_is_moving(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if not snapshot.body_present:
        return "No body pose detected, so I can't determine movement."
    speed = snapshot.movement_speed
    if snapshot.moving:
        return (
            f"The person is moving (smoothed speed {speed:.1f} px/frame)."
        )
    if speed > 0.5:
        return (
            f"Minor movement detected ({speed:.1f} px/frame) — below the "
            "movement threshold."
        )
    return "No significant movement detected — the person is still."


def _arm_state(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    if not snapshot.body_present or not snapshot.arm_states:
        return "No arm data available — the arms are not visible."
    parts: list[str] = []
    for side in ("left", "right"):
        state = snapshot.arm_states.get(side, "UNKNOWN")
        angle = snapshot.arm_angles.get(side) if snapshot.arm_angles else None
        angle_text = f" ({angle:.0f}° elbow)" if angle is not None else ""
        parts.append(f"{side} arm: {state}{angle_text}")
    return " · ".join(parts) + "."


def _summary(snapshot: Optional[SceneSnapshot]) -> str:
    if snapshot is None:
        return _no_data()
    counts = (
        f"persons={snapshot.persons}, faces={snapshot.faces}, "
        f"hands={snapshot.hands}, objects={len(snapshot.objects)}, "
        f"gestures={len(snapshot.gestures)}"
    )
    objects = (
        ", ".join(sorted(set(snapshot.objects))) if snapshot.objects else "none"
    )
    gestures = (
        ", ".join(sorted(set(snapshot.gestures))) if snapshot.gestures else "none"
    )
    return (
        f"Vision summary — {counts}. "
        f"Objects: {objects}. Gestures: {gestures}."
    )
