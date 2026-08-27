"""AI Vision Engine: SceneSnapshot + conversation -> LLM -> answer.

The engine is the single entry point for the AI layer:

* Builds the grounded system prompt + vision context (ContextBuilder).
* Keeps the RAM-only conversation history (VisionConversation).
* Selects and instantiates the LLM provider from the settings
  (Ollama / OpenAI-compatible / Mock, offline mode respected).
* Runs every LLM call in a worker thread — the camera/vision loop and
  the GUI event loop are never blocked.
* Is fully UI-agnostic (no Qt imports): the UI wraps the callbacks.

The engine only ever sends structured context to the LLM — never frames,
landmark arrays or images.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from app.ai.conversation import VisionConversation
from app.ai.context import SYSTEM_PROMPT, build_scene_context
from app.ai.providers.base import LLMProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import (
    API_KEY_ENV,
    OpenAICompatibleProvider,
)
from app.config.settings import SettingsService
from app.core.types import SceneSnapshot
from app.utils.logging_setup import get_logger

log = get_logger("ai.engine")

#: Ask callbacks: token stream / completion / failure.
TokenCallback = Callable[[str], None]
DoneCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]

#: Maximum history messages sent to the LLM (keeps the context bounded).
_HISTORY_LIMIT = 12

#: Provider availability is probed over the network — cache results so
#: the UI never blocks the GUI thread on repeated probes.
_STATUS_TTL = 10.0


def api_key_from_env() -> Optional[str]:
    """API key from the environment (never from settings/logs)."""
    return os.environ.get(API_KEY_ENV)


class AIVisionEngine:
    """Coordinates providers, context and conversation."""

    def __init__(self, settings_service: SettingsService) -> None:
        self._settings_service = settings_service
        self._conversation = VisionConversation()
        #: Last completed LLM call duration (real measurement).
        self.last_llm_duration_ms: Optional[float] = None
        #: provider key -> (monotonic timestamp, status dict)
        self._status_cache: dict[str, tuple[float, dict]] = {}
        #: Cancel event of the active call (None when idle).
        self._active_cancel: Optional[threading.Event] = None
        self._active_lock = threading.Lock()

    # ------------------------------------------------------------------
    def cancel_current(self) -> bool:
        """Abort the running LLM call cooperatively (user pressed STOP).

        Returns True when a call was active and got cancelled.
        """
        with self._active_lock:
            event = self._active_cancel
        if event is None:
            return False
        event.set()
        return True

    # ------------------------------------------------------------------
    @property
    def conversation(self) -> VisionConversation:
        return self._conversation

    def clear_chat(self) -> None:
        self._conversation.clear()

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------
    def build_provider(self) -> LLMProvider:
        """Instantiate the provider configured in the settings.

        Offline mode forces the mock provider; a failing provider never
        raises here — problems surface as readable ask() errors.
        """
        settings = self._settings_service.settings
        if settings.offline_mode:
            return MockProvider(
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout,
            )
        if settings.llm_provider == "mock":
            return MockProvider(
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout,
            )
        if settings.llm_provider == "openai_compatible":
            return OpenAICompatibleProvider(
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout,
                api_key=api_key_from_env(),
            )
        return OllamaProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model or "llama3",
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    def provider_status(self, force: bool = True) -> dict[str, str]:
        """Honest status summary for the UI.

        ``force=True`` probes the provider synchronously (network call,
        up to a few seconds — use it from worker threads only). With
        ``force=False`` a fresh cached probe result is returned when
        available; otherwise a probe still happens (compatibility with
        synchronous callers/tests). Mock providers answer instantly.
        """
        settings = self._settings_service.settings
        provider = self.build_provider()
        if provider.is_mock:
            status = "mock"
            detail = (
                "OFFLINE MODE — MOCK fallback"
                if settings.offline_mode
                else "Mock (dev fallback)"
            )
        else:
            cached = self._status_cache.get(provider.key)
            if cached is not None:
                cached_at, cached_status = cached
                if not force and time.monotonic() - cached_at < _STATUS_TTL:
                    return cached_status
            status = provider.availability()
            if provider.key == "ollama":
                detail = (
                    f"Ollama · {provider.model}"
                    if status == "online"
                    else "Ollama not reachable"
                )
            else:
                key_ok = bool(api_key_from_env())
                detail = (
                    f"{settings.llm_base_url} · key {'set' if key_ok else 'NOT set'}"
                )
        result = {
            "provider": provider.key,
            "status": status,
            "detail": detail,
        }
        self._status_cache[provider.key] = (time.monotonic(), result)
        return result

    def provider_status_cached(self, ttl: float = _STATUS_TTL):
        """Non-blocking status: cached probe result, or None.

        Mock providers resolve instantly (no cache needed). Used by the
        GUI thread so the UI never performs network I/O.
        """
        provider = self.build_provider()
        if provider.is_mock:
            return self.provider_status(force=False)
        cached = self._status_cache.get(provider.key)
        if cached is not None:
            cached_at, status = cached
            if time.monotonic() - cached_at < ttl:
                return status
        return None

    def list_ollama_models(self) -> list[str]:
        """Models known to a running Ollama instance (empty if offline)."""
        settings = self._settings_service.settings
        if settings.offline_mode:
            return []
        provider = OllamaProvider(
            base_url=settings.llm_base_url, timeout=3.0
        )
        return provider.list_models()

    # ------------------------------------------------------------------
    # Asking
    # ------------------------------------------------------------------
    def build_messages(
        self,
        query: str,
        snapshot: Optional[SceneSnapshot],
        memory_context: str = "",
    ) -> list[dict[str, str]]:
        """System prompt + scene context + bounded history + the query.

        ``memory_context`` (session memory) is only included for LOCAL
        providers (Ollama, Mock) — external providers never receive the
        user's notes. The gate lives here, in one place.
        """
        provider = self.build_provider()
        context = build_scene_context(snapshot)
        system = f"{SYSTEM_PROMPT}\n\n{context}"
        if memory_context and provider.key in ("ollama", "mock"):
            system += f"\n\n{memory_context}"
        elif memory_context:
            log.debug(
                "Memory excluded from context for provider '%s' "
                "(external providers never receive session memory)",
                provider.key,
            )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system}
        ]
        messages.extend(self._conversation.to_llm_messages(limit=_HISTORY_LIMIT))
        messages.append({"role": "user", "content": query})
        return messages

    def ask(
        self,
        query: str,
        snapshot: Optional[SceneSnapshot],
        on_token: Optional[TokenCallback] = None,
        on_done: Optional[DoneCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        memory_context: str = "",
    ) -> None:
        """Blocking ask — call from a worker thread.

        The query is recorded in the conversation together with the
        answer, so follow-up questions have context.
        """
        provider = self.build_provider()
        self._conversation.add("user", query)
        import time as _time

        cancel_event = threading.Event()
        with self._active_lock:
            self._active_cancel = cancel_event
        try:
            started = _time.perf_counter()
            try:
                response = provider.complete(
                    self.build_messages(
                        query, snapshot, memory_context=memory_context
                    ),
                    on_token=on_token,
                    cancel_event=cancel_event,
                )
                self.last_llm_duration_ms = (
                    _time.perf_counter() - started
                ) * 1000.0
            except Exception as exc:  # noqa: BLE001 — readable errors to the UI
                if cancel_event.is_set():
                    log.info("LLM call cancelled by user")
                    if on_error is not None:
                        on_error("cancelled")
                    return
                log.warning("LLM call failed (%s): %s", provider.key, exc)
                message = f"LLM UNAVAILABLE — {exc}"
                if on_error is not None:
                    on_error(message)
                return
        finally:
            with self._active_lock:
                if self._active_cancel is cancel_event:
                    self._active_cancel = None
        self._conversation.add("assistant", response.text)
        if on_done is not None:
            on_done(response.text)

    def ask_async(
        self,
        query: str,
        snapshot: Optional[SceneSnapshot],
        on_token: Optional[TokenCallback] = None,
        on_done: Optional[DoneCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        memory_context: str = "",
    ) -> threading.Thread:
        """Non-blocking ask; returns the worker thread."""

        def _work() -> None:
            self.ask(query, snapshot, on_token, on_done, on_error,
                     memory_context=memory_context)

        thread = threading.Thread(
            target=_work, name="ai-llm-call", daemon=True
        )
        thread.start()
        return thread
