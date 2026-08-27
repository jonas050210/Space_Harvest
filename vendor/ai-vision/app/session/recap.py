"""Deterministic session recap (Phase 26) — real data, offline, RAM-only.

Builds a human-readable summary of the current session from bounded
in-memory data (blink stats, gaze samples, scene events). No LLM, no
persistence — the recap is exactly what the session recorded, nothing
more.
"""

from __future__ import annotations

from typing import Sequence


def summarize_events(events: Sequence) -> dict[str, int]:
    """Count events by type (deterministic, bounded input)."""
    counts: dict[str, int] = {}
    for event in events:
        name = str(getattr(event, "type", event)).split(".")[-1]
        counts[name] = counts.get(name, 0) + 1
    return counts


def build_session_recap(
    duration_s: float,
    blink_stats: dict,
    gaze_samples: int,
    gaze_coverage: float,
    events: Sequence,
    now_running: bool = True,
) -> str:
    """One readable recap block — every number comes from real data."""
    if duration_s <= 0 and not now_running:
        return (
            "No session data yet — start the camera and the recap "
            "appears here automatically."
        )
    blink_stats = blink_stats or {}
    minutes = duration_s / 60.0
    lines = [
        f"Session length: {fmt_duration(duration_s)}.",
    ]
    lines.append(
        f"Blinks: {blink_stats.get('count', 0)} total, "
        f"{blink_stats.get('rate_per_min', 0)} per minute."
    )
    lines.append(f"Gaze samples recorded: {gaze_samples}.")
    if gaze_coverage > 0:
        lines.append(
            f"Screen coverage: {gaze_coverage * 100:.0f}% of the view "
            "was looked at."
        )
    summary = summarize_events(events)
    if summary:
        event_text = " · ".join(
            f"{name} ×{count}" for name, count in sorted(summary.items())
        )
        lines.append(f"Scene events: {event_text}.")
    else:
        lines.append("Scene events: none recorded.")
    if minutes >= 1.0:
        lines.append(
            f"Average: {blink_stats.get('rate_per_min', 0)} blinks/min "
            f"over {minutes:.1f} minutes."
        )
    return "\n".join(lines)


def fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
