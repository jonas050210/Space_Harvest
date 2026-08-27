"""Pure gallery filter/sort logic (unit-testable, UI-independent).

Match-quality filters derive from the stored analysis' prompt-match
verdict — records without analysis fall into "unanalyzed". Sorting by
best match uses the match score (unanalyzed records sort last).
"""

from __future__ import annotations

from typing import Optional, Sequence

from app.image.storage import ImageRecord

#: (key, label) pairs for the gallery filter combo.
FILTERS: tuple[tuple[str, str], ...] = (
    ("all", "ALL"),
    ("generated", "GENERATED"),
    ("uploaded", "UPLOADED"),
    ("analyzed", "ANALYZED"),
    ("unanalyzed", "UNANALYZED"),
    ("good", "GOOD MATCH"),
    ("partial", "PARTIAL"),
    ("weak", "WEAK"),
    ("failed", "FAILED"),
)

#: (key, label) pairs for the gallery sort combo.
SORTS: tuple[tuple[str, str], ...] = (
    ("newest", "NEWEST"),
    ("oldest", "OLDEST"),
    ("best_match", "BEST MATCH"),
    ("provider", "PROVIDER"),
    ("version", "VERSION"),
)


def match_verdict(record: ImageRecord) -> Optional[str]:
    """The stored prompt-match verdict (None when not analyzed)."""
    analysis = record.analysis
    if not analysis:
        return None
    match = analysis.get("prompt_match")
    if not isinstance(match, dict) or not match.get("checked"):
        return None
    verdict = str(match.get("verdict", ""))
    return verdict or None


def match_score(record: ImageRecord) -> float:
    """The stored match score (0.0 for unanalyzed records)."""
    analysis = record.analysis
    if not analysis:
        return 0.0
    match = analysis.get("prompt_match")
    if not isinstance(match, dict):
        return 0.0
    score = match.get("score")
    return float(score) if score is not None else 0.0


def filter_records(
    records: Sequence[ImageRecord], filter_key: str
) -> list[ImageRecord]:
    """Apply a gallery filter; unknown keys behave like 'all'."""
    key = filter_key or "all"
    if key in ("all", ""):
        return list(records)
    if key == "generated":
        return [r for r in records if r.source == "generated"]
    if key == "uploaded":
        return [r for r in records if r.source == "uploaded"]
    if key == "analyzed":
        return [r for r in records if r.analysis is not None]
    if key == "unanalyzed":
        return [r for r in records if r.analysis is None]
    if key in ("good", "partial", "weak"):
        verdict_name = {"good": "good match", "partial": "partial match",
                        "weak": "weak match"}[key]
        return [r for r in records if match_verdict(r) == verdict_name]
    return list(records)  # "failed" is handled by the queue, not records


def sort_records(
    records: Sequence[ImageRecord], sort_key: str
) -> list[ImageRecord]:
    """Sort records; unknown keys fall back to newest-first."""
    key = sort_key or "newest"
    items = list(records)
    if key == "oldest":
        items.sort(key=lambda r: r.timestamp)
    elif key == "best_match":
        items.sort(key=lambda r: (match_score(r), r.timestamp), reverse=True)
    elif key == "provider":
        items.sort(key=lambda r: (r.provider, -r.timestamp))
    elif key == "version":
        items.sort(key=lambda r: (r.parent_id, r.version))
    else:
        items.sort(key=lambda r: r.timestamp, reverse=True)
    return items
