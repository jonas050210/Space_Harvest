"""Local extension hooks (Phase 28) — no marketplace, no remote code.

User plugins live in ``data/extensions/*.py`` and are loaded only when
the ``extensions_enabled`` setting is on. A broken plugin is isolated:
it cannot crash the app.
"""

from app.extensions.registry import (
    ExtensionHooks,
    ExtensionInfo,
    ExtensionRegistry,
)

__all__ = ["ExtensionRegistry", "ExtensionInfo", "ExtensionHooks"]
