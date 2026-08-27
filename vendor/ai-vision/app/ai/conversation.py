"""RAM-only vision conversation history.

The chat history (user questions, AI answers, event notes) lives only in
memory and is bounded. No camera or vision data is persisted. The history
is passed to the LLM as message list together with the *current* scene
context, which is what allows follow-up questions like "Which one is
larger?" without storing images or landmark data anywhere.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system"
    text: str
    timestamp: float = field(default_factory=time.monotonic)


class VisionConversation:
    """Bounded in-memory conversation history.

    Args:
        max_messages: Maximum number of messages kept (oldest dropped).
    """

    def __init__(self, max_messages: int = 40) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self._messages: deque[ChatMessage] = deque(maxlen=max_messages)

    def add(self, role: str, text: str) -> None:
        self._messages.append(ChatMessage(role=role, text=text))

    def clear(self) -> None:
        self._messages.clear()

    def messages(self, limit: Optional[int] = None) -> list[ChatMessage]:
        items = list(self._messages)
        if limit is not None:
            items = items[-limit:]
        return items

    def to_llm_messages(self, limit: Optional[int] = None) -> list[dict[str, str]]:
        """Message list for LLM APIs (role/content pairs)."""
        return [
            {"role": message.role, "content": message.text}
            for message in self.messages(limit)
            if message.role in ("user", "assistant")
        ]

    def __len__(self) -> int:
        return len(self._messages)
