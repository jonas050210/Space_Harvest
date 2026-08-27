"""User feedback -> deterministic prompt refinement.

Feedback entries (correct/wrong/partial + free text) are translated into
concrete prompt adjustments: rating-dependent framing plus keyword
mapping for the most common complaints (arm, face, pose, realism, ...).
The refinement is deterministic and honest — it adjusts the prompt, it
does not claim the image will be fixed. Optional LLM polish can be
applied on top by the caller (via the AI engine).
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.core.types import FeedbackEntry, SceneSnapshot

#: Keyword -> prompt guidance (lowercase matching). Ordered: more specific
#: terms first so broad keywords like "arm" don't shadow refinements.
_KEYWORD_GUIDANCE: tuple[tuple[str, str], ...] = (
    ("arm", "correct arm anatomy and positioning"),
    ("hand", "correct hand anatomy (five fingers, natural pose)"),
    ("gesicht", "improve the facial structure and proportions"),
    ("face", "improve face fidelity and proportions"),
    ("pose", "correct the body pose to match the described scene"),
    ("kopf", "correct the head position and proportion"),
    ("schulter", "correct the shoulder alignment and anatomy"),
    ("beine", "correct the leg anatomy and positioning"),
    ("realistic", "make it more photorealistic"),
    ("realistisch", "make it more photorealistic"),
    ("color", "adjust the color palette"),
    ("farbe", "adjust the color palette"),
    ("blurry", "increase sharpness and detail"),
    ("unscharf", "increase sharpness and detail"),
    ("dark", "brighten the scene"),
    ("dunkel", "brighten the scene"),
    ("hell", "improve the lighting balance"),
    ("lighting", "improve the lighting and shadows"),
    ("beleuchtung", "improve the lighting and shadows"),
    ("hintergrund", "correct the background"),
    ("background", "correct the background"),
    ("links", "adjust the spatial composition (move elements left)"),
    ("rechts", "adjust the spatial composition (move elements right)"),
    ("left", "adjust the spatial composition (move elements left)"),
    ("right", "adjust the spatial composition (move elements right)"),
    ("weiter links", "move the subject further to the left"),
    ("weiter rechts", "move the subject further to the right"),
    ("größer", "increase the prominence and size of the subject"),
    ("grosser", "increase the prominence and size of the subject"),
    ("larger", "increase the prominence and size of the subject"),
    ("kleiner", "reduce the size of the subject"),
    ("smaller", "reduce the size of the subject"),
    ("details", "add more fine detail and texture"),
    ("augen", "correct the eyes and gaze direction"),
    ("eyes", "correct the eyes and gaze direction"),
    ("proportion", "fix the body and face proportions"),
    ("proportionen", "fix the body and face proportions"),
)

#: Category -> prompt guidance (structured feedback 3.0).
CATEGORY_GUIDANCE: dict[str, str] = {
    "object": "correct the depicted objects and their arrangement",
    "pose": "correct the body pose to match the described scene",
    "face": "improve the facial structure and proportions",
    "arm": "correct arm anatomy and positioning",
    "hand": "correct hand anatomy (five fingers, natural pose)",
    "lighting": "improve the lighting and shadows",
    "background": "correct the background",
    "composition": "improve the composition and framing",
    "style": "adjust the visual style and consistency",
    "detail": "add more fine detail and texture",
    "other": "",
}

#: Refusal-style ratings are handled honestly: if nothing actionable is
#: known, the refinement states it instead of inventing changes.
_RATING_FRAMES = {
    "wrong": "the previous version was incorrect",
    "partial": "the previous version was only partially correct",
    "correct": "the previous version was good",
}


def _rating_of(entry) -> str:
    """Rating of a FeedbackEntry OR a raw dict (tolerant input)."""
    if isinstance(entry, dict):
        return str(entry.get("rating", "partial"))
    return str(getattr(entry, "rating", "partial"))


def _text_of(entry) -> str:
    """Text of a FeedbackEntry OR a raw dict (tolerant input)."""
    if isinstance(entry, dict):
        return str(entry.get("text", ""))
    return str(getattr(entry, "text", ""))


def refine_prompt(
    base_prompt: str,
    feedback: Iterable[FeedbackEntry],
    snapshot: Optional[SceneSnapshot] = None,
) -> str:
    """Deterministically refine a prompt from feedback entries.

    Feedback text may carry a leading ``[category]`` tag (feedback 3.0);
    the category contributes its guidance mapping. Always returns a
    prompt; when the feedback contains nothing actionable, the base
    prompt is kept and the honest note is appended.
    """
    entries = list(feedback)
    if not entries:
        return base_prompt

    frames = [
        _RATING_FRAMES.get(_rating_of(entry),
                           "the previous version had issues")
        for entry in entries
        if _rating_of(entry) != "correct"
    ]
    guidance: list[str] = []
    text_parts: list[str] = []
    for entry in entries:
        raw_text = _text_of(entry).strip()
        category = ""
        if raw_text.startswith("[") and "]" in raw_text:
            category, raw_text = raw_text[1:].split("]", 1)
            category = category.strip().lower()
        if category in CATEGORY_GUIDANCE and CATEGORY_GUIDANCE[category]:
            hint = CATEGORY_GUIDANCE[category]
            if hint not in guidance:
                guidance.append(hint)
        text = raw_text.strip()
        if text:
            text_parts.append(text)
        for keyword, hint in _KEYWORD_GUIDANCE:
            if keyword in text.lower() and hint not in guidance:
                guidance.append(hint)

    if not guidance and not text_parts and not frames:
        return base_prompt

    additions: list[str] = []
    if frames:
        additions.append("; ".join(dict.fromkeys(frames)))
    if guidance:
        additions.append(" — " + "; ".join(guidance))
    if text_parts:
        additions.append(" (user note: " + "; ".join(text_parts[:3]) + ")")

    suffix = ". " + ". ".join(additions) + "."
    return base_prompt.rstrip() + suffix
