"""HTTP helpers shared by the LLM and image providers (stdlib only)."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Optional

from app.utils.logging_setup import get_logger

log = get_logger("ai.providers.http")

_DEFAULT_TIMEOUT = 30.0


def http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    """POST JSON, return (status_code, parsed_json). Raises on errors."""
    data = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url, data=data, headers=request_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from {url}: {body[:300]}"
        ) from exc
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc


def http_get_json(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    """GET JSON; returns (status_code, parsed_json). Raises on errors."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc


def http_get_bytes(url: str, timeout: float = _DEFAULT_TIMEOUT) -> bytes:
    """GET raw bytes (used to fetch generated image URLs)."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc
