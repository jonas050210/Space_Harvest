"""SceneSnapshot -> image prompt builder.

Converts the current scene into a safe, controlled image-generation
prompt that only uses detected information. Explicitly never:
* reproduces real persons or faces,
* invents objects, colors, distances or identities,
* sends any camera imagery.

Direction information (gaze quadrant, head yaw) is translated into
generic scene language ("the figure is looking towards the right").
"""

from __future__ import annotations

from typing import Optional

from app.core.types import SceneSnapshot

#: Prefix that keeps the generation abstract (no real persons).
_SAFE_PREFIX = (
    "Create a stylized, non-photorealistic visual representation of a "
    "scene containing"
)
_SAFE_SUFFIX = (
    ". Abstract illustration style, clean composition, no text, "
    "no identifiable real persons, no logos."
)

#: Gaze quadrant -> scene language (normalized 0..1 coordinates).
_GAZE_DIRECTIONS = {
    ("top", "left"): "the figure is looking towards the upper left",
    ("top", "right"): "the figure is looking towards the upper right",
    ("bottom", "left"): "the figure is looking towards the lower left",
    ("bottom", "right"): "the figure is looking towards the lower right",
}


def build_scene_prompt(snapshot: Optional[SceneSnapshot]) -> Optional[str]:
    """Build an image prompt from a SceneSnapshot.

    Returns None when there is nothing detected to describe — no prompt
    is fabricated from thin air.
    """
    if snapshot is None:
        return None

    items: list[str] = []
    directions: list[str] = []

    if snapshot.persons:
        items.append(
            "one stylized human figure" if snapshot.persons == 1
            else f"{snapshot.persons} stylized human figures"
        )

    if snapshot.objects:
        for name in sorted(set(snapshot.objects)):
            if name == "person":
                continue  # persons are represented generically above
            items.append(f"a {name}")

    if snapshot.hands:
        items.append(
            "a hand" if snapshot.hands == 1 else f"{snapshot.hands} hands"
        )
    if snapshot.gestures:
        gesture_names = sorted(set(snapshot.gestures))
        items.append(
            "showing the gesture: " + ", ".join(gesture_names)
        )

    # Direction information (generic, non-identifying).
    if snapshot.gaze is not None:
        x, y, _confidence = snapshot.gaze
        quadrant = ("top" if y < 0.5 else "bottom", "left" if x < 0.5 else "right")
        directions.append(_GAZE_DIRECTIONS[quadrant])
    if snapshot.head_pose is not None:
        yaw, pitch, _roll = snapshot.head_pose
        if abs(yaw) > 10:
            directions.append(
                "the figure's head is turned towards the "
                + ("right" if yaw > 0 else "left")
            )
        if abs(pitch) > 10:
            directions.append(
                "the figure's head is tilted "
                + ("down" if pitch > 0 else "up")
            )

    if not items:
        return None

    body = ", ".join(items)
    prompt = f"{_SAFE_PREFIX} {body}"
    if directions:
        prompt += "; " + ", ".join(directions)
    return prompt + _SAFE_SUFFIX
