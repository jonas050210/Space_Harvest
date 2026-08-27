"""Context builder: SceneSnapshot -> structured LLM prompt context.

Privacy-first: only counts, class names, gesture names and scalar
summaries reach the LLM. No landmark arrays, no raw vision data, no
images. The grounding system prompt instructs the model to only use the
provided context.
"""

from __future__ import annotations

from typing import Optional

from app.core.types import SceneSnapshot

#: System prompt that grounds the model in the vision context.
SYSTEM_PROMPT = (
    "You are the AI Vision assistant of a local computer vision app. "
    "You receive a structured VISION CONTEXT below, produced by a normal "
    "webcam pipeline. You may ONLY use information contained in that "
    "context (and the conversation history). "
    "If something is not in the context — e.g. distances, colors, "
    "identities, emotions — answer exactly: "
    "\"I can't determine that from the available vision data.\" "
    "Never invent objects, colors, distances, or information about "
    "persons. Vision data is approximate; phrase statements accordingly "
    "(e.g. 'the detector reports a laptop at 94% confidence')."
)


def build_scene_context(snapshot: Optional[SceneSnapshot]) -> str:
    """Render a SceneSnapshot as a compact structured text block."""
    if snapshot is None:
        return (
            "VISION CONTEXT\n"
            "No vision data available (camera not running or no detections)."
        )

    lines: list[str] = ["VISION CONTEXT"]
    lines.append(f"Persons: {snapshot.persons}")
    lines.append(f"Faces: {snapshot.faces}")

    if snapshot.objects:
        lines.append("Objects:")
        for name in snapshot.objects:
            lines.append(f"- {name}")
    else:
        lines.append("Objects: none detected")

    lines.append(f"Hands: {snapshot.hands}")
    if snapshot.gestures:
        lines.append("Gestures:")
        for gesture in snapshot.gestures:
            lines.append(f"- {gesture}")
    else:
        lines.append("Gestures: none detected")

    if snapshot.gaze is not None:
        x, y, confidence = snapshot.gaze
        lines.append(
            f"Gaze: x={x:.2f}, y={y:.2f} (normalized), confidence={confidence:.0%}"
        )
    else:
        lines.append("Gaze: not available")

    if snapshot.head_pose is not None:
        yaw, pitch, roll = snapshot.head_pose
        lines.append(
            f"Head pose: yaw={yaw:+.0f}°, pitch={pitch:+.0f}°, roll={roll:+.0f}° "
            "(approximate)"
        )
    else:
        lines.append("Head pose: not available")

    # Phase 9: body/arm/movement details (scalars only, privacy-safe).
    if snapshot.body_present:
        if snapshot.arm_states:
            arms = ", ".join(
                f"{side}={state}"
                for side, state in sorted(snapshot.arm_states.items())
            )
            lines.append(f"Arm states: {arms}")
        if snapshot.arm_angles:
            angles = ", ".join(
                f"{side}={angle:.0f}°" if angle is not None else f"{side}=unknown"
                for side, angle in sorted(snapshot.arm_angles.items())
            )
            lines.append(f"Arm angles (elbow): {angles}")
        if snapshot.shoulder_angle_deg is not None:
            lines.append(
                f"Shoulder tilt: {snapshot.shoulder_angle_deg:+.0f}°"
            )
        if snapshot.head_position is not None:
            hx, hy = snapshot.head_position
            lines.append(f"Head position: x={hx:.2f}, y={hy:.2f} (normalized)")
        lines.append(f"Movement: {'moving' if snapshot.moving else 'still'}"
                     f" (speed {snapshot.movement_speed:.1f} px/frame)")

    return "\n".join(lines)

