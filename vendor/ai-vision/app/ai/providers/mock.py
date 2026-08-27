"""Mock LLM provider — development/offline fallback, clearly labeled.

The mock never fabricates vision facts: it answers by echoing the vision
context it received and reformulating it. Every response is prefixed with
``[MOCK]`` so it can never be mistaken for a real model. It exists so the
AI layer can be developed and smoke-tested without any LLM service, and it
is the automatic fallback in offline mode.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from app.ai.providers.base import (
    CANCELLED_MESSAGE,
    LLMProvider,
    LLMResponse,
    TokenCallback,
)

#: Marker prefix of every mock response.
MOCK_PREFIX = "[MOCK] "


class MockProvider(LLMProvider):
    """Deterministic, context-echoing fake provider."""

    key = "mock"
    display_name = "Mock (dev fallback)"

    def __init__(self, temperature: float = 0.3, timeout: float = 30.0,
                 max_tokens: int = 512) -> None:
        super().__init__(
            model="mock-1",
            temperature=temperature,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    @property
    def is_mock(self) -> bool:
        return True

    def availability(self) -> str:
        return "online"

    def complete(
        self,
        messages: list[dict[str, str]],
        on_token: Optional[TokenCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> LLMResponse:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError(CANCELLED_MESSAGE)
        context = _find_vision_context(messages)
        query = _last_user_query(messages)
        answer = MOCK_PREFIX + _mock_answer(context, query)
        # Simulate streaming in small chunks (dev-only behaviour).
        if on_token is not None:
            for i in range(0, len(answer), 12):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError(CANCELLED_MESSAGE)
                on_token(answer[i:i + 12])
                time.sleep(0.002)
        return LLMResponse(
            text=answer, provider=self.key, model="mock-1", is_mock=True
        )


def _find_vision_context(messages: list[dict[str, str]]) -> str:
    for message in messages:
        if message.get("role") == "system":
            return message.get("content", "")
    return ""


def _last_user_query(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _mock_answer(context: str, query: str) -> str:
    """Reformulate the vision context — never invents anything."""
    vision = context.split("VISION CONTEXT", 1)
    block = vision[1].strip() if len(vision) > 1 else context
    if "No vision data available" in block:
        return (
            "The vision context contains no data, so I can't describe "
            "the scene."
        )
    return (
        f"Question: '{query}'. "
        f"Based on the vision context: {block}"
    )
