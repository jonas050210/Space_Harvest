"""Ollama provider — local LLM via the Ollama HTTP API.

Talks to ``{base_url}/api/chat`` with streaming enabled (newline-delimited
JSON). The base URL and model are configurable; no API key needed (local
service). Implemented with the standard library — no extra dependencies.
"""

from __future__ import annotations

import json
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
from app.ai.providers.http import http_get_json
from app.utils.logging_setup import get_logger

log = get_logger("ai.providers.ollama")

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3"


class OllamaProvider(LLMProvider):
    """Local Ollama chat backend (streaming)."""

    key = "ollama"
    display_name = "Ollama (local)"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.3,
        timeout: float = 30.0,
        max_tokens: int = 512,
    ) -> None:
        super().__init__(
            model=model or DEFAULT_MODEL,
            temperature=temperature,
            timeout=timeout,
            max_tokens=max_tokens,
        )
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    def availability(self) -> str:
        try:
            http_get_json(f"{self._base_url}/api/version", timeout=1.5)
            return "online"
        except RuntimeError:
            return "offline"

    def list_models(self) -> list[str]:
        try:
            _status, data = http_get_json(
                f"{self._base_url}/api/tags", timeout=2.0
            )
        except RuntimeError as exc:
            log.debug("Ollama model list failed: %s", exc)
            return []
        models = data.get("models", [])
        return [
            entry["name"]
            for entry in models
            if isinstance(entry, dict) and entry.get("name")
        ]

    # ------------------------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, str]],
        on_token: Optional[TokenCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
            },
        }
        request = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        parts: list[str] = []
        deadline = time.monotonic() + self._timeout
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:
                for raw_line in response:
                    if time.monotonic() > deadline:
                        break
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError(CANCELLED_MESSAGE)
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = (
                        chunk.get("message", {}).get("content", "")
                        if isinstance(chunk.get("message"), dict)
                        else ""
                    )
                    if text:
                        parts.append(text)
                        if on_token is not None:
                            on_token(text)
                    if chunk.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Ollama error (HTTP {exc.code}). Is the service running "
                f"and is model '{self._model}' pulled?"
            ) from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise RuntimeError(
                f"Ollama is not reachable at {self._base_url}: {exc}"
            ) from exc

        if not parts:
            raise RuntimeError("Ollama returned an empty response.")
        return LLMResponse(
            text="".join(parts), provider=self.key, model=self._model
        )
