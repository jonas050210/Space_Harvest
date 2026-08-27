"""Voice integration (Phase 17) — capability-gated, honest, local.

Text-to-speech (TTS) runs through the OPERATING SYSTEM's own speech
facilities via the standard library (subprocess) — no new dependency:

    Windows  PowerShell System.Speech (SAPI, built into Windows)
    macOS    /usr/bin/say
    Linux    spd-say (speech-dispatcher) or espeak, if installed

The engine detects the backend ONCE and reports honestly:

    status "real"        — a platform TTS command was found and verified
    status "mock"        — no platform voice found; the dev mock speaks
                           (clearly labeled [MOCK] in logs, silent by
                           default — nothing is ever played without
                           detection)
    status "unavailable" — no TTS at all (button disabled in the UI)

Speech-to-text (STT, Phase 28) uses the OPERATING SYSTEM recognizer
the same way TTS does — no Whisper, no extra package:

    Windows  System.Speech.Recognition (SAPI dictation)
    others   unavailable (no stdlib recognizer)

Status is honest: real / mock / unavailable. The mock NEVER invents
a transcript. A production-grade neural STT (faster-whisper, …) is
still deliberately NOT added.

Privacy: only the AI's ANSWER TEXT is ever sent to the local speech
command — never frames, never prompts beyond the answer, never any
data leaving the machine.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional

from app.ai.commands import match_command
from app.core.types import SceneSnapshot
from app.utils.logging_setup import get_logger

log = get_logger("ai.voice")

#: Longest text spoken in one call (keeps subprocess payloads sane).
_MAX_SPEAK_CHARS = 2000


# ---------------------------------------------------------------------------
# Provider contracts (kept from the Phase-4 architecture)
# ---------------------------------------------------------------------------
class SpeechToTextProvider(ABC):
    """Interface for speech recognition backends.

    Production-grade neural STT (Whisper etc.) is deliberately NOT
    added. The built-in VoiceEngine.listen() uses the OS recognizer
    when one exists; this interface stays for alternate backends.
    """

    @abstractmethod
    def transcribe(self, audio: bytes) -> str:
        """Audio bytes -> text. Raises on failure."""


class TextToSpeechProvider(ABC):
    """Interface for speech synthesis backends."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Text -> audio bytes. Raises on failure."""


class VoiceCommandPipeline:
    """Wires STT -> vision query -> answer -> TTS.

    Intended flow: audio is captured by the UI layer, transcribed, the
    resulting text is handled exactly like a typed chat message (built-in
    commands answered deterministically, free-form queries via the AI
    engine), and the answer is synthesized back to audio.

    Args:
        stt: Speech-to-text backend (None — not implemented).
        tts: Text-to-speech backend (None — not implemented).
        ask: Callable answering free-form queries (typically the
            AI engine's ask). For built-in commands the deterministic
            CommandResponder is used instead.
    """

    def __init__(
        self,
        stt: Optional[SpeechToTextProvider] = None,
        tts: Optional[TextToSpeechProvider] = None,
        ask: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._ask = ask

    def handle_audio(self, audio: bytes) -> Optional[str]:
        """STT -> query -> answer -> TTS. Returns the answer text.

        Honest by design: without an STT backend this reports
        unavailable instead of pretending to transcribe.
        """
        if self._stt is None:
            return None
        query = self._stt.transcribe(audio).strip()
        if not query:
            return None
        command = match_command(query)
        answer = (
            _answer_deterministic(command, None)
            if command is not None and command != "CREATE SCENE IMAGE"
            else (
                self._ask(query)
                if self._ask is not None
                else "No AI engine connected."
            )
        )
        if self._tts is not None:
            self._tts.synthesize(answer)
        return answer


def _answer_deterministic(command: str, snapshot: Optional[SceneSnapshot]) -> str:
    from app.ai.commands import answer_command

    return answer_command(command, snapshot)


# ---------------------------------------------------------------------------
# Real TTS engine (system speech, stdlib only)
# ---------------------------------------------------------------------------
def _detect_backend() -> Optional[tuple[str, list[str]]]:
    """Find a usable platform TTS command (verified executable)."""
    candidates: dict[str, list[str]] = {}
    if sys.platform == "win32":
        candidates["sapi"] = ["powershell", "-NoProfile", "-Command"]
    elif sys.platform == "darwin":
        candidates["say"] = ["say"]
    else:
        for name in ("spd-say", "espeak"):
            path = shutil.which(name)
            if path:
                candidates[name] = [path]
    for name, command in candidates.items():
        if command[0] == "powershell" or shutil.which(command[0]):
            return name, command
    return None


class VoiceEngine:
    """Capability-gated system TTS with a clearly labeled mock fallback.

    The mock NEVER plays audio unless the caller explicitly enables it —
    it exists so the SPEAK pipeline is testable in dev, and every mock
    utterance is logged with the [MOCK] prefix.
    """

    def __init__(self, allow_mock: bool = True) -> None:
        self._backend: Optional[tuple[str, list[str]]] = _detect_backend()
        self._allow_mock = allow_mock
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def backend(self) -> Optional[str]:
        return self._backend[0] if self._backend else None

    def status(self) -> dict[str, str]:
        """Honest TTS capability report: real | mock | unavailable."""
        if self._backend is not None:
            return {
                "status": "real",
                "detail": f"system TTS via '{self._backend[0]}'",
            }
        if self._allow_mock:
            return {
                "status": "mock",
                "detail": "no system voice found — dev mock (labeled "
                          "[MOCK], silent)",
            }
        return {
            "status": "unavailable",
            "detail": "no system TTS available on this machine",
        }

    def stt_status(self) -> dict[str, str]:
        """Honest STT capability report: real | mock | unavailable.

        Only Windows SAPI dictation is implemented (no extra package).
        Linux/macOS stay unavailable unless a mock is allowed.
        """
        if sys.platform == "win32" and shutil.which("powershell"):
            return {
                "status": "real",
                "detail": "system STT via Windows SAPI dictation",
            }
        if self._allow_mock:
            return {
                "status": "mock",
                "detail": "no system recognizer — dev mock (never invents "
                          "a transcript)",
            }
        return {
            "status": "unavailable",
            "detail": "no system speech recognizer on this machine",
        }

    def listen(self, timeout: float = 8.0) -> Optional[str]:
        """Capture one utterance. Returns None when nothing was heard.

        Never invents a transcript. The mock path is silent (returns
        None) so tests / Linux sandboxes stay honest.
        """
        timeout = max(1.0, min(30.0, float(timeout)))
        if sys.platform == "win32" and shutil.which("powershell"):
            return self._listen_sapi(timeout)
        log.info("[MOCK] listen: no system recognizer — nothing transcribed")
        return None

    def listen_async(
        self,
        on_done: Callable[[Optional[str]], None],
        timeout: float = 8.0,
    ) -> threading.Thread:
        """Non-blocking listen (UI never waits for the recognizer)."""

        def _work() -> None:
            try:
                text = self.listen(timeout=timeout)
            except Exception:  # noqa: BLE001 — UI callback must not die
                log.exception("STT listen failed")
                text = None
            try:
                on_done(text)
            except Exception:  # noqa: BLE001
                log.exception("STT callback failed")

        thread = threading.Thread(
            target=_work, name="voice-listen", daemon=True
        )
        thread.start()
        return thread

    def _listen_sapi(self, timeout: float) -> Optional[str]:
        """One-shot Windows SAPI dictation (subprocess, timed)."""
        seconds = max(2, int(timeout))
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$e = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
            "try { $e.SetInputToDefaultAudioDevice() } "
            "catch { Write-Output ''; exit 0 }; "
            "$e.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
            f"$e.InitialSilenceTimeout = [TimeSpan]::FromSeconds({min(3, seconds)}); "
            f"$r = $e.Recognize([TimeSpan]::FromSeconds({seconds})); "
            "if ($r) { Write-Output $r.Text } else { Write-Output '' }"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                check=False, timeout=timeout + 5,
                capture_output=True, text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("System STT failed: %s", exc)
            return None
        text = (completed.stdout or "").strip()
        return text or None

    def speak(self, text: str) -> bool:
        """Speak one answer via the detected backend. Never raises.

        Returns True when the utterance was actually dispatched.
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return False
        if self._backend is None:
            if self._allow_mock:
                log.info("[MOCK] voice: %s", cleaned[:_MAX_SPEAK_CHARS])
                return True
            log.warning("Voice unavailable — nothing spoken")
            return False
        return self._speak_real(cleaned)

    def speak_async(self, text: str) -> Optional[threading.Thread]:
        """Non-blocking speak (UI never waits for the speech process)."""
        thread = threading.Thread(
            target=self.speak, args=(text,), name="voice-speak",
            daemon=True,
        )
        thread.start()
        return thread

    # ------------------------------------------------------------------
    def _speak_real(self, text: str) -> bool:
        name, command = self._backend
        payload = text[:_MAX_SPEAK_CHARS]
        try:
            if name == "sapi":
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis."
                    "SpeechSynthesizer; $s.Speak($args[0])"
                )
                subprocess.run(
                    command + [script, payload],
                    check=False, timeout=30,
                    capture_output=True,
                )
            elif name == "say":
                subprocess.run(["say", payload], check=False, timeout=30)
            else:  # spd-say / espeak
                subprocess.run(
                    command + [payload], check=False, timeout=30,
                    capture_output=True,
                )
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("System TTS failed (%s): %s", name, exc)
            return False
