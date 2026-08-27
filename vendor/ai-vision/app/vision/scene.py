"""Scene snapshot: structured per-frame scene summary.

Built by the pipeline from the module results. Contains only counts,
class/gesture names and scalar summaries — no raw landmarks and no image
data. This is the input structure for the AI Vision layer in Phase 4.
"""

from __future__ import annotations

from app.core.types import SceneSnapshot, VisionResult


def build_scene_snapshot(result: VisionResult) -> SceneSnapshot:
    """Summarize a pipeline result into a SceneSnapshot. Never raises."""
    gaze = None
    if result.gaze is not None and result.gaze.valid:
        gaze = (result.gaze.x, result.gaze.y, result.gaze.confidence)

    pose = None
    if result.head_pose is not None and result.head_pose.valid:
        pose = (result.head_pose.yaw, result.head_pose.pitch, result.head_pose.roll)

    body_present = bool(result.body is not None and result.body.present)
    arm_states = dict(result.body.arm_states) if body_present else {}
    arm_angles = dict(result.body.arm_angles) if body_present else {}
    shoulder_deg = (
        result.body.shoulder_angle_deg if body_present else None
    )
    movement_speed = result.body.movement_speed if body_present else 0.0
    moving = movement_speed > 2.5

    head_position = None
    if body_present and result.body.head_position is not None:
        frame = result.frame
        if frame is not None and frame.shape[0] > 0 and frame.shape[1] > 0:
            hx, hy = result.body.head_position
            head_position = (round(hx / frame.shape[1], 3),
                             round(hy / frame.shape[0], 3))

    return SceneSnapshot(
        faces=len(result.faces),
        persons=len(result.persons),
        objects=[obj.class_name for obj in result.objects],
        hands=len(result.hands),
        gestures=[g.gesture for g in result.gestures],
        gaze=gaze,
        head_pose=pose,
        body_present=body_present,
        arm_states=arm_states,
        arm_angles=arm_angles,
        shoulder_angle_deg=shoulder_deg,
        head_position=head_position,
        movement_speed=round(movement_speed, 2),
        moving=moving,
    )
