"""Local-only plugin loader (Phase 28).

Design rules (honest, privacy-first):

* Plugins are plain ``.py`` files in a local folder. Nothing is
  downloaded, signed or auto-updated.
* Loading is opt-in (``extensions_enabled``). Default is off.
* Each plugin is imported in isolation. An exception in one file is
  recorded as a failure and the rest still load.
* A plugin may register extra deterministic commands and extra image
  provider *factories*. It cannot replace the camera, the settings
  store or the privacy contract.
* Recursive imports, hidden files and more than ``_MAX_PLUGINS`` files
  are ignored.
"""

from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

from app.utils.logging_setup import get_logger

log = get_logger("extensions")

_MAX_PLUGINS = 20
_MAX_BYTES = 256 * 1024


@dataclass
class ExtensionInfo:
    """One discovered plugin (loaded or failed)."""

    name: str
    path: Path
    version: str = ""
    loaded: bool = False
    error: str = ""


@dataclass
class ExtensionHooks:
    """What a plugin is allowed to register."""

    commands: dict[str, tuple[str, ...]] = field(default_factory=dict)
    command_handlers: dict[str, Callable[..., str]] = field(default_factory=dict)
    image_providers: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def add_command(
        self,
        canonical: str,
        aliases: tuple[str, ...] | list[str],
        handler: Optional[Callable[..., str]] = None,
    ) -> None:
        key = (canonical or "").strip().upper()
        if not key:
            return
        cleaned = tuple(
            a.strip().lower() for a in aliases if isinstance(a, str) and a.strip()
        )
        if cleaned:
            self.commands[key] = cleaned
        if handler is not None:
            self.command_handlers[key] = handler

    def add_image_provider(self, key: str, factory: Callable[..., Any]) -> None:
        cleaned = (key or "").strip().lower()
        if cleaned and callable(factory):
            self.image_providers[cleaned] = factory


class ExtensionRegistry:
    """Discover + load local plugins. Thread-safe, never raises to callers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hooks = ExtensionHooks()
        self._loaded: list[ExtensionInfo] = []

    @property
    def hooks(self) -> ExtensionHooks:
        return self._hooks

    def infos(self) -> list[ExtensionInfo]:
        with self._lock:
            return list(self._loaded)

    def load(self, directory: Path, enabled: bool = True) -> list[ExtensionInfo]:
        """Load every ``*.py`` in ``directory``. Safe if the folder is missing."""
        infos: list[ExtensionInfo] = []
        if not enabled:
            with self._lock:
                self._loaded = []
                self._hooks = ExtensionHooks()
            return infos
        folder = Path(directory)
        if not folder.is_dir():
            with self._lock:
                self._loaded = []
                self._hooks = ExtensionHooks()
            return infos
        hooks = ExtensionHooks()
        files = sorted(
            p for p in folder.glob("*.py")
            if p.is_file() and not p.name.startswith(("_", "."))
        )[:_MAX_PLUGINS]
        for path in files:
            info = self._load_one(path, hooks)
            infos.append(info)
        with self._lock:
            self._hooks = hooks
            self._loaded = infos
        loaded = sum(1 for i in infos if i.loaded)
        log.info(
            "Extensions: %d loaded · %d failed from %s",
            loaded, len(infos) - loaded, folder,
        )
        return infos

    def extra_command_patterns(self) -> dict[str, tuple[str, ...]]:
        with self._lock:
            return dict(self._hooks.commands)

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Optional[str]:
        with self._lock:
            handler = self._hooks.command_handlers.get(command)
        if handler is None:
            return None
        try:
            return handler(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — plugin must not crash chat
            log.warning("Extension command %s failed: %s", command, exc)
            return f"Extension command '{command}' failed: {exc}"

    def image_provider_factory(self, key: str) -> Optional[Callable[..., Any]]:
        with self._lock:
            return self._hooks.image_providers.get((key or "").lower())

    # ------------------------------------------------------------------
    def _load_one(self, path: Path, hooks: ExtensionHooks) -> ExtensionInfo:
        info = ExtensionInfo(name=path.stem, path=path)
        try:
            if path.stat().st_size > _MAX_BYTES:
                info.error = f"plugin larger than {_MAX_BYTES} bytes — skipped"
                return info
            module = _import_path(path)
        except Exception as exc:  # noqa: BLE001
            info.error = f"import failed: {exc}"
            log.warning("Extension %s import failed: %s", path.name, exc)
            return info
        meta = getattr(module, "EXTENSION", None)
        if isinstance(meta, dict):
            info.name = str(meta.get("name") or path.stem)
            info.version = str(meta.get("version") or "")
        register = getattr(module, "register", None)
        if not callable(register):
            info.error = "no register(hooks) function"
            return info
        try:
            register(hooks)
        except Exception as exc:  # noqa: BLE001
            info.error = f"register() failed: {exc}"
            log.warning("Extension %s register failed: %s", path.name, exc)
            return info
        info.loaded = True
        return info


def _import_path(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"ai_vision_lab_ext_{path.stem}", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
