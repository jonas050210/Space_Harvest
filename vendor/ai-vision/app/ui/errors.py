"""Human-readable error formatting — the WHAT/WHY/HOW TO FIX contract.

Technical error text stays in the log; the UI shows a structured,
actionable message instead of raw exceptions. Every user-facing error in
the product follows the same shape:

    WHAT        — what happened (one line)
    WHY         — why it happened (one line)
    HOW TO FIX  — what the user can do (one line)
    DETAILS     — technical detail, collapsed by default (never a raw
                  traceback in the primary view)
"""

from __future__ import annotations


class FriendlyError(Exception):
    """A user-presentable error: carries the WHAT/WHY/HOW TO FIX parts.

    Technical detail goes into ``details`` (shown only when expanded).
    """

    def __init__(
        self,
        what: str,
        why: str = "",
        fix: str = "",
        details: str = "",
    ) -> None:
        super().__init__(what)
        self.what = what
        self.why = why
        self.fix = fix
        self.details = details

    def as_dict(self) -> dict[str, str]:
        return {
            "what": self.what,
            "why": self.why,
            "fix": self.fix,
            "details": self.details,
        }


def format_error_text(
    what: str,
    why: str = "",
    fix: str = "",
    details: str = "",
) -> str:
    """Render the WHAT/WHY/HOW TO FIX contract as readable text."""
    lines = ["WHAT: " + what]
    if why:
        lines.append("WHY: " + why)
    if fix:
        lines.append("HOW TO FIX: " + fix)
    if details:
        lines.append("DETAILS: " + details)
    return "\n".join(lines)


def _clean_technical(text: str, limit: int = 140) -> str:
    """Trim + remove traceback artifacts from raw error text.

    Normal users never see internal stack traces — this runs before a
    raw message can reach a WHAT/WHY/HOW TO FIX block.
    """
    cleaned = (text or "").strip()
    if "Traceback" in cleaned:
        # Keep the final exception line if present (it is the message).
        tail = cleaned.rsplit("\n", 1)[-1].strip()
        cleaned = tail if tail and "Traceback" not in tail else ""
    if not cleaned:
        cleaned = "Unknown error."
    return cleaned[:limit]


def split_camera_error(error_text: str) -> tuple[str, str, str, str]:
    """Map a raw camera/capture error to (what, why, fix, details).

    Camera errors are frequent (device unplugged, permissions, occupied
    device) — users get the WHAT/WHY/HOW TO FIX contract, never a raw
    exception string.
    """
    text = (error_text or "").strip()
    lowered = text.lower()
    what = "The camera stopped or could not be used."

    if "busy" in lowered or "in use" in lowered or "occupied" in lowered:
        why = "The camera is in use by another application."
        fix = "Close other apps that use the camera, then press ⟳ and start again."
    elif "permission" in lowered or "denied" in lowered or "access" in lowered:
        why = "The operating system denied camera access."
        fix = ("Windows: Settings → Privacy → Camera → allow desktop apps. "
               "Then press ⟳.")
    elif "disconnect" in lowered or "unplug" in lowered or "removed" in lowered:
        why = "The camera was disconnected."
        fix = "Reconnect the camera and press ⟳ to rescan."
    elif "not found" in lowered or "no camera" in lowered or "can't open" in lowered \
            or "cannot open" in lowered or "index" in lowered:
        why = "No usable camera was found at the selected index."
        fix = "Connect a webcam, press ⟳ to rescan and select it."
    elif "frame" in lowered:
        why = "The camera opened but delivered no frames."
        fix = "Close other apps using the camera and retry."
    else:
        why = _clean_technical(text) or "Unknown camera error."
        fix = "Press ⟳ to rescan, or see logs/vision_lab.log for details."
    return what, why, fix, _clean_technical(text, 400)


def split_llm_error(error_text: str) -> tuple[str, str, str, str]:
    """Map a raw LLM/provider error to (what, why, fix, details)."""
    text = (error_text or "").strip()
    lowered = text.lower()
    what = "The AI provider could not answer."

    if "cancelled" in lowered:
        return (
            "The request was cancelled.",
            "You pressed STOP while the model was answering.",
            "Nothing to do — ask a new question when ready.",
            text[:400],
        )
    if "api key" in lowered or "no api key" in lowered or "unauthorized" in lowered:
        why = "No API key is configured."
        fix = "Set the AI_VISION_LAB_API_KEY environment variable and retry."
    elif "not reachable" in lowered or "connection refused" in lowered \
            or "unreachable" in lowered or "refused" in lowered:
        why = "The provider server is not reachable."
        fix = "Start the provider (e.g. `ollama serve`) and check its URL under SYSTEM."
    elif "timeout" in lowered or "timed out" in lowered:
        why = "The provider did not answer in time."
        fix = "Increase the timeout (SYSTEM tab) or reduce provider load."
    elif "not found" in lowered or "404" in text:
        why = "The requested model was not found."
        fix = "Install the model (e.g. `ollama pull llama3`) or pick another one."
    else:
        why = _clean_technical(text) or "Unknown provider error."
        fix = "Deterministic commands still work offline; see DETAILS."
    return what, why, fix, _clean_technical(text, 400)


def format_provider_error(provider_name: str, error_text: str) -> str:
    """Build a friendly multi-line error description.

    Args:
        provider_name: Display name of the provider (e.g. "SD WebUI").
        error_text: The raw error message from the provider call.

    Returns a readable text block: title, provider, reason, action.
    """
    text = (error_text or "").strip()
    lowered = text.lower()

    if "cancelled" in lowered:
        reason = "The operation was cancelled."
        action = "Nothing to do — you can start a new generation."
    elif "api key" in lowered or "no api key" in lowered:
        reason = "No API key is configured."
        action = (
            "Set the AI_VISION_LAB_API_KEY environment variable, then "
            "retry. The key is never stored in settings."
        )
    elif "not found" in lowered or "404" in text:
        reason = "The requested model or resource was not found."
        action = (
            "Check the model name (SYSTEM tab shows detected models) and "
            "make sure the model is installed."
        )
    elif "500" in text:
        reason = "The provider server returned HTTP 500."
        action = f"Check whether {provider_name} is running and healthy, then retry."
    elif "timeout" in lowered or "timed out" in lowered:
        reason = "The provider did not answer in time."
        action = (
            "Increase the timeout (SYSTEM tab) or check the provider's "
            "load, then retry."
        )
    elif (
        "not reachable" in lowered
        or "cannot reach" in lowered
        or "connection refused" in lowered
        or "unreachable" in lowered
    ):
        reason = f"{provider_name} is not reachable."
        action = (
            f"Start {provider_name} and verify its URL (SYSTEM tab), then retry."
        )
    elif "non-png" in lowered or "corrupt" in lowered or "invalid image" in lowered:
        reason = "The provider returned invalid image data."
        action = "Retry the generation; if it persists, switch providers."
    elif "does not support" in lowered:
        reason = text
        action = "Choose a provider that supports this feature."
    else:
        reason = _clean_technical(text) or "Unknown provider error."
        action = "See logs/vision_lab.log for technical details."

    return (
        f"IMAGE GENERATION FAILED\n"
        f"Provider: {provider_name}\n"
        f"Reason: {reason}\n"
        f"Suggested action: {action}"
    )


def split_provider_error(
    provider_name: str, error_text: str
) -> tuple[str, str, str, str]:
    """Map a raw provider error to (what, why, fix, details) — the WHAT/
    WHY/HOW TO FIX contract used by toasts and dialogs."""
    friendly = format_provider_error(provider_name, error_text)
    lines = friendly.splitlines()
    # Keep the first line as the WHAT title, then fold the rest.
    what = lines[0].replace("IMAGE GENERATION FAILED", "Image generation failed")
    why = " · ".join(
        line for line in lines if line.startswith("Provider:")
        or line.startswith("Reason:")
    )
    fix = next(
        (line.replace("Suggested action: ", "") for line in lines
         if line.startswith("Suggested action:")),
        "Check SYSTEM and try again.",
    )
    details = (error_text or "").strip()[:400]
    return what, why, fix, details
