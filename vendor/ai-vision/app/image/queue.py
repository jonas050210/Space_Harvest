"""Generation queue: ordered, observable, cancellable image jobs.

One worker thread drains the queue sequentially. Statuses:

    QUEUED -> GENERATING -> COMPLETED | FAILED | CANCELLED

A failure in one job never stops the queue or the vision pipeline.
Cancellation is cooperative: a queued job is cancelled immediately; a
generating job is flagged and the provider aborts at its next check (a
blocking HTTP call cannot be interrupted mid-flight).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Optional

from app.utils.logging_setup import get_logger

log = get_logger("image.queue")

#: Job status constants (shown in the UI verbatim).
QUEUED = "QUEUED"
GENERATING = "GENERATING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

_TERMINAL = {COMPLETED, FAILED, CANCELLED}

#: Maximum finished jobs kept in memory (bounded memory for long
#: sessions; the gallery reads persisted records from disk anyway).
_MAX_KEPT = 60


def format_job_status(job: "GenerationJob") -> str:
    """Honest one-line job status for the UI.

    A percentage is only shown when the provider actually reported
    progress — otherwise the status reads "GENERATING…" (no invented
    percent values, no fake progress bars).
    """
    if job.status == GENERATING:
        if job.progress > 0.01:
            return f"#{job.id} GENERATING {int(job.progress * 100)}%"
        return f"#{job.id} GENERATING…"
    return f"#{job.id} {job.status}"



@dataclass
class GenerationJob:
    """One queued image generation request."""

    id: int
    prompt: str
    provider_key: str = "mock"
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    seed: int = -1
    model: str = ""
    preset: str = "none"
    init_image: Optional[bytes] = None  # img2img source (PNG bytes)
    mask_image: Optional[bytes] = None  # inpaint mask (PNG, optional)
    parent_id: str = ""                 # file name of the previous version
    version: int = 1                    # iteration version
    status: str = QUEUED
    error: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    duration_ms: Optional[float] = None
    progress: float = 0.0
    result: Any = None           # GeneratedImage | None
    record: Any = None           # ImageRecord | None
    cancel_event: Event = field(default_factory=Event, repr=False)


class GenerationQueue:
    """Thread-safe FIFO job queue with status callbacks."""

    def __init__(self, max_pending: int = 50) -> None:
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._jobs: list[GenerationJob] = []
        self._max_pending = max_pending
        self._next_id = 1

    # ------------------------------------------------------------------
    def enqueue(self, job: GenerationJob) -> GenerationJob:
        with self._condition:
            job.id = self._next_id
            self._next_id += 1
            self._jobs.append(job)
            if len(self._jobs) > self._max_pending:
                # Drop oldest terminal, then oldest queued. Never drop a
                # job that is currently generating — the worker still
                # owns it and the UI must keep seeing it.
                drop_at: Optional[int] = None
                for index, existing in enumerate(self._jobs):
                    if existing.status in _TERMINAL:
                        drop_at = index
                        break
                if drop_at is None:
                    for index, existing in enumerate(self._jobs):
                        if existing.status == QUEUED:
                            existing.status = CANCELLED
                            existing.error = "Dropped: queue full"
                            drop_at = index
                            break
                if drop_at is not None:
                    self._jobs.pop(drop_at)
            # Memory bound: never keep more than the most recent terminal
            # jobs in memory (each job holds prompt text + PNG bytes).
            # Long sessions with hundreds of generations stay bounded;
            # the gallery reads persisted records from disk anyway.
            terminal = [j for j in self._jobs if j.status in _TERMINAL]
            if len(terminal) > _MAX_KEPT:
                keep_ids = {id(j) for j in terminal[-_MAX_KEPT:]}
                self._jobs = [
                    j for j in self._jobs
                    if j.status not in _TERMINAL or id(j) in keep_ids
                ]
            self._condition.notify_all()
        log.info(
            "Generation job #%d queued (%s, %s)", job.id, job.provider_key, job.status
        )
        return job

    def pop_next(self, timeout: float = 2.0) -> Optional[GenerationJob]:
        """Block until a QUEUED job is available; None on timeout."""
        with self._condition:
            while True:
                for job in self._jobs:
                    if job.status == QUEUED:
                        return job
                self._condition.wait(timeout=timeout)
                # Re-check after the wait.
                for job in self._jobs:
                    if job.status == QUEUED:
                        return job
                return None

    def update(self, job: GenerationJob) -> None:
        with self._condition:
            self._condition.notify_all()

    def get(self, job_id: int) -> Optional[GenerationJob]:
        with self._lock:
            for job in self._jobs:
                if job.id == job_id:
                    return job
        return None

    def cancel(self, job_id: int) -> bool:
        """Cancel a job; returns True if the job existed."""
        job = self.get(job_id)
        if job is None:
            return False
        if job.status == QUEUED:
            job.status = CANCELLED
            job.finished_at = time.monotonic()
            log.info("Generation job #%d cancelled while queued", job_id)
        elif job.status == GENERATING:
            job.cancel_event.set()
            log.info("Generation job #%d cancel requested", job_id)
        return True

    def active_jobs(self, limit: int = 20) -> list[GenerationJob]:
        """Most recent jobs (any status), newest first."""
        with self._lock:
            return list(reversed(self._jobs[-limit:]))

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs if j.status == QUEUED)

    def clear_finished(self) -> None:
        """Drop terminal jobs from the in-memory list (UI cleanup)."""
        with self._lock:
            self._jobs = [
                j for j in self._jobs if j.status not in _TERMINAL
            ]
