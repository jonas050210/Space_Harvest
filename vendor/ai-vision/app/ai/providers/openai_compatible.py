"""OpenAI-compatible chat provider (any endpoint with the Chat Completions API).

Works with cloud APIs and local servers that expose the OpenAI API shape
(LM Studio, llama.cpp server, vLLM, Ollama's /v1 endpoint, ...). Streaming
via SSE is parsed from the raw HTTP stream. The API key is read from the
environment only — never from settings, source code or logs.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from app.ai.providers.base import (
    CANCELLED_MESSAGE,
    LLMProvider,
    LLMResponse,
    TokenCallback,
)
from app.utils.logging_setup import get_logger

log = get_logger("ai.providers.openai")

#: Environment variable for the API key (documented in the README).
API_KEY_ENV = "AI_VISION_LAB_API_KEY"

DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OpenAICompatibleProvider(LLMProvider):
    """Chat Completions backend with SSE streaming support."""

    key = "openai_compatible"
    display_name = "OpenAI Compatible"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "",
        temperature: float = 0.3,
        timeout: float = 30.0,
        max_tokens: int = 512,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_tokens=max_tokens,
        )
        self._base_url = base_url.rstrip("/")
        # Explicit argument wins; otherwise the environment variable is
        # the single source of truth (never settings or code).
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)

    # ------------------------------------------------------------------
    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def availability(self) -> str:
        if not self._api_key:
            return "configured"  # reachable unknown; needs a key
        return "configured"

    def list_models(self) -> list[str]:
        return []

    # ------------------------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, str]],
        on_token: Optional[TokenCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> LLMResponse:
        if not self._api_key:
            raise RuntimeError(
                "No API key configured. Set the "
                f"{API_KEY_ENV} environment variable."
            )

        model = self._model or "gpt-4o-mini"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        parts: list[str] = []
        deadline = time.monotonic() + self._timeout
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" not in content_type:
                    # Server ignored stream=True: plain JSON response.
                    body = response.read().decode("utf-8", errors="replace")
                    data = json.loads(body)
                    text = _extract_text(data)
                    if on_token is not None and text:
                        on_token(text)
                    return LLMResponse(
                        text=text, provider=self.key, model=model
                    )
                for raw_line in response:
                    if time.monotonic() > deadline:
                        break
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError(CANCELLED_MESSAGE)
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line[len("data:"):].strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_text(data)
                    if text:
                        parts.append(text)
                        if on_token is not None:
                            on_token(text)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"LLM API error (HTTP {exc.code}): {body}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise RuntimeError(f"LLM API unreachable at {self._base_url}: {exc}") from exc

        if not parts:
            raise RuntimeError("LLM API returned an empty response.")
        return LLMResponse(
            text="".join(parts), provider=self.key, model=model
        )


def _extract_text(data: dict) -> str:
    try:
        choices = data.get("choices", [])
        if not choices:
            return ""
        delta = choices[0].get("delta", {})
        content = delta.get("content")
        if content:
            return str(content)
        # Non-streaming shape.
        message = choices[0].get("message", {})
        return str(message.get("content", ""))
    except (AttributeError, IndexError, KeyError):
        return ""
