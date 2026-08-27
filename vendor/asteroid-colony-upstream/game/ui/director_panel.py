"""Compact Colony Director panel for objectives, warnings, and next actions."""

from ursina import Entity, Text, Vec3, camera, color
from .. import director


def create_director_panel(app_ref):
    panel = Entity(parent=camera.ui, model="quad", color=color.rgba(12, 20, 30, 0.9), scale=(0.46, 0.24), position=Vec3(-0.55, -0.28, -0.15))
    title = Text(text="COLONY DIRECTOR  [TAB]", parent=camera.ui, position=Vec3(-0.75, -0.19, -0.16), scale=0.7, color=color.azure)
    objective = Text(text="", parent=camera.ui, position=Vec3(-0.75, -0.235, -0.16), scale=0.52, origin=(-0.5, 0))
    recommendation = Text(text="", parent=camera.ui, position=Vec3(-0.75, -0.31, -0.16), scale=0.50, origin=(-0.5, 0), color=color.cyan)
    alert = Text(text="", parent=camera.ui, position=Vec3(-0.75, -0.385, -0.16), scale=0.48, origin=(-0.5, 0), color=color.orange)

    def refresh():
        if not panel.enabled:
            return
        data = director.snapshot(app_ref.state)
        objective.text = "GOAL: " + data["objective"]
        recommendation.text = "NEXT: " + data["recommendation"]
        alert.text = "ALERT: " + data["alerts"][0][1] if data["alerts"] else f"REGION: {data['region']} | MILESTONES: {data['milestones']}"

    def toggle():
        visible = not panel.enabled
        for element in (panel, title, objective, recommendation, alert):
            element.enabled = visible
        if visible:
            refresh()

    return {"panel": panel, "refresh": refresh, "toggle": toggle}
