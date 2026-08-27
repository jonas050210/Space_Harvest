"""LLM provider interface and shared HTTP helpers.

All providers are implemented with the Python standard library
(``urllib``) — no additional dependencies. Providers never import Qt, so
they stay fully unit-testable and can run in any worker thread.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.utils.logging_setup import get_logger

log = get_logger("ai.providers")

TokenCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]

#: Raised when a call is aborted cooperatively (user pressed STOP).
CANCELLED_MESSAGE = "cancelled by user"


@dataclass
class LLMResponse:
    """Result of one completed LLM call."""

    text: str
    provider: str
    model: str = ""
    is_mock: bool = False
    extra: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Interface every LLM backend implements."""

    #: Provider key used in settings (llm_provider).
    key: str = ""
    #: Human-readable name for the UI.
    display_name: str = ""

    def __init__(
        self,
        model: str = "",
        temperature: float = 0.3,
        timeout: float = 30.0,
        max_tokens: int = 512,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_mock(self) -> bool:
        return False

    def availability(self) -> str:
        """One of: online | offline | configured | error — honest status."""
        return "configured"

    def list_models(self) -> list[str]:
        """Models known to this provider (empty when unsupported)."""
        return []

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        on_token: Optional[TokenCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> LLMResponse:
        """Complete a chat; streams partial text via on_token if provided.

        ``cancel_event`` (optional) aborts cooperatively: providers check
        it between stream chunks and raise ``RuntimeError(CANCELLED_MESSAGE)``.

        Raises: RuntimeError with a readable message on failure.
        """
