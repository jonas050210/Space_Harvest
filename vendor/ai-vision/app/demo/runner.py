"""Scripted demo orchestration for the full product loop.

The DemoRunner drives a real MainWindow through the complete flow —
live vision, AI query, generation, analysis, feedback, regeneration,
compare, gallery — using the demo frame source (real models, no fake
data). Every step has a predicate and a timeout; results are reported
through a callback (GUI overlay or console) and summarized at the end.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.utils.logging_setup import get_logger

log = get_logger("demo.runner")

#: One demo step: key, label, predicate, timeout (seconds).
@dataclass
class DemoStep:
    key: str
    label: str
    predicate: Callable[["DemoRunner"], bool]
    timeout: float = 60.0
    status: str = "pending"  # pending | running | passed | failed
    detail: str = ""
    started_at: Optional[float] = None
    duration_ms: Optional[float] = None


StepCallback = Callable[[DemoStep], None]


class DemoRunner:
    """Executes the demo steps against a prepared MainWindow."""

    def __init__(
        self,
        window,
        on_step: Optional[StepCallback] = None,
        poll_interval: float = 0.05,
    ) -> None:
        self.window = window
        self._on_step = on_step
        self._poll_interval = poll_interval
        self._steps = self._build_steps()
        self.completed = False
        self._aborted = False

        # State flags consumed by the step predicates/triggers.
        self._ai_answered = False
        self._feedback_done = False
        self._compare_done = False
        self._gallery_count = 0
        self._summarized = False

    # ------------------------------------------------------------------
    def abort(self) -> None:
        """Stop the demo at the next poll (window closing / shutdown).

        The demo runs on the GUI thread and pumps the event loop — an
        abort flag makes close-during-demo exit immediately instead of
        waiting for step timeouts.
        """
        self._aborted = True

    # ------------------------------------------------------------------
    @property
    def steps(self) -> list[DemoStep]:
        return self._steps

    def _build_steps(self) -> list[DemoStep]:
        window = self.window

        def latest():
            return window.controller.latest()[1]

        def job_completed(version: int = 1):
            return any(
                j.status == "COMPLETED" and j.version >= version
                for j in window.image_engine.queue.active_jobs()
            )

        return [
            DemoStep("app", "INITIALIZING", lambda r: window.isVisible()),
            DemoStep(
                "vision", "CAMERA",
                lambda r: r._ensure_demo_camera_started(),
                timeout=60.0,
            ),
            DemoStep(
                "objects", "OBJECTS",
                lambda r: latest() is not None and bool(latest().objects),
                timeout=60.0,
            ),
            DemoStep(
                "person", "PERSON",
                lambda r: latest() is not None and bool(latest().persons),
                timeout=60.0,
            ),
            DemoStep(
                "body", "BODY",
                lambda r: latest() is not None
                and latest().body is not None
                and latest().body.present,
                timeout=60.0,
            ),
            DemoStep(
                "arms", "ARMS",
                lambda r: latest() is not None
                and latest().body is not None
                and any(
                    state != "UNKNOWN"
                    for state in latest().body.arm_states.values()
                ),
                timeout=60.0,
            ),
            DemoStep(
                "scene", "SCENE",
                lambda r: window._current_snapshot() is not None,
                timeout=40.0,
            ),
            DemoStep(
                "ai", "AI",
                lambda r: self._ai_answered,
                timeout=30.0,
            ),
            DemoStep("generate", "GENERATION", lambda r: job_completed(1), timeout=90.0),
            DemoStep(
                "analyze", "ANALYSIS",
                lambda r: any(
                    j.status == "COMPLETED" and j.record is not None
                    and j.record.analysis is not None
                    for j in window.image_engine.queue.active_jobs()
                ),
                timeout=120.0,
            ),
            DemoStep(
                "match", "MATCH",
                lambda r: self._match_verdict() is not None,
                timeout=60.0,
            ),
            DemoStep(
                "feedback", "FEEDBACK",
                lambda r: self._feedback_done,
                timeout=30.0,
            ),
            DemoStep(
                "regenerate", "REGENERATION",
                lambda r: job_completed(2),
                timeout=120.0,
            ),
            DemoStep(
                "compare", "COMPARE",
                lambda r: self._compare_done,
                timeout=30.0,
            ),
            DemoStep(
                "gallery", "GALLERY",
                lambda r: self._gallery_count >= 2,
                timeout=30.0,
            ),
            DemoStep("final", "COMPLETE", lambda r: self._summarized),
        ]

    # ------------------------------------------------------------------
    # Step actions (triggered when the previous step passed)
    # ------------------------------------------------------------------
    def _ensure_demo_camera_started(self) -> bool:
        """Start the demo camera once discovery completed (idempotent)."""
        window = self.window
        if (
            not window.controller.is_running
            and window.camera_panel.selected_camera_index is not None
        ):
            window._on_start_clicked()
        return (
            window.controller.is_running
            and window.controller.latest()[2].total_frames >= 5
        )

    def _trigger(self, step: DemoStep) -> None:
        window = self.window
        if step.key == "ai":
            self._ai_answered = False
            before = len(window.ai_panel._blocks)
            window.ai_panel.submit("Was sehe ich?")
            # Deterministic commands answer synchronously.
            self._ai_answered = len(window.ai_panel._blocks) > before
        elif step.key == "generate":
            from app.image.prompt_builder import build_scene_prompt

            snapshot = window._current_snapshot()
            prompt = build_scene_prompt(snapshot) or "a person at a desk with a laptop and a cup"
            window.image_panel.prompt_edit.setPlainText(prompt)
            window.image_panel._on_generate()
        elif step.key == "feedback":
            self._feedback_done = False
            completed = [
                j for j in window.image_engine.queue.active_jobs()
                if j.status == "COMPLETED" and j.record is not None
            ]
            if completed:
                record = completed[-1].record
                window._select_record(record, window.image_store)
                window._on_feedback("partial", "ARM", "Der Arm ist falsch")
                self._feedback_done = True
        elif step.key == "regenerate":
            window._regenerate_with_feedback()
        elif step.key == "compare":
            self._compare_done = False
            v2 = [
                j for j in window.image_engine.queue.active_jobs()
                if j.status == "COMPLETED" and j.version >= 2
                and j.record is not None
            ]
            if v2:
                window._select_record(v2[-1].record, window.image_store)
                window._compare_selected()
                self._compare_done = (
                    window.preview_workspace.compare_view._pixmap_a is not None
                )
        elif step.key == "gallery":
            window.gallery_panel.refresh()
            self._gallery_count = window.gallery_panel.list_widget.count()
        elif step.key == "final":
            self._summarized = True

    # ------------------------------------------------------------------
    def _match_verdict(self) -> Optional[str]:
        for job in self.window.image_engine.queue.active_jobs():
            if job.record is not None and job.record.analysis:
                return job.record.analysis.get("prompt_match", {}).get("verdict")
        return None

    # ------------------------------------------------------------------
    def run(self) -> list[DemoStep]:
        """Execute all steps; returns the final step list with statuses."""
        for step in self._steps:
            step.status = "running"
            step.started_at = time.monotonic()
            if self._on_step is not None:
                self._on_step(step)
            self._trigger(step)
            deadline = time.monotonic() + step.timeout
            passed = False
            detail = ""
            while time.monotonic() < deadline:
                if self._aborted:
                    detail = "aborted by shutdown"
                    break
                try:
                    if step.predicate(self):
                        passed = True
                        break
                except Exception as exc:  # noqa: BLE001 — demo must continue
                    detail = str(exc)
                    break
                self._pump()
            step.status = "passed" if passed else "failed"
            step.duration_ms = round(
                (time.monotonic() - step.started_at) * 1000.0, 1
            )
            if step.key == "analyze" and passed:
                step.detail = f"verdict: {self._match_verdict() or '?'}"
            if detail:
                step.detail = detail
            if self._on_step is not None:
                self._on_step(step)
            log.info(
                "Demo step %s: %s (%.0f ms)%s",
                step.key, step.status, step.duration_ms,
                f" — {step.detail}" if step.detail else "",
            )
            if self._aborted:
                # Remaining steps are never started — shutdown is in
                # progress and must win.
                for remaining in self._steps[
                    self._steps.index(step) + 1:
                ]:
                    remaining.status = "failed"
                    remaining.detail = "aborted by shutdown"
                    if self._on_step is not None:
                        self._on_step(remaining)
                break
        self.completed = all(step.status == "passed" for step in self._steps)
        return self._steps

    def _pump(self) -> None:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        time.sleep(self._poll_interval)

    def summary(self) -> str:
        """Printable demo summary."""
        lines = ["=== DEMO SUMMARY ==="]
        for step in self._steps:
            mark = "PASS" if step.status == "passed" else "FAIL"
            duration = (
                f" ({step.duration_ms:.0f} ms)" if step.duration_ms else ""
            )
            lines.append(f"[{mark}] {step.label}{duration}"
                         + (f" — {step.detail}" if step.detail else ""))
        lines.append(
            "DEMO COMPLETE" if self.completed
            else "DEMO FINISHED WITH FAILURES"
        )
        return "\n".join(lines)
