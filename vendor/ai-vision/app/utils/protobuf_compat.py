"""Compatibility shim for MediaPipe + newer protobuf.

MediaPipe 0.10.x still calls ``MessageFactory.GetPrototype``. Protobuf 5+
removed that method (replaced by ``GetMessageClass``). Without a pin or
this patch, importing mediapipe prints:

    AttributeError: 'MessageFactory' object has no attribute 'GetPrototype'

and later task creation can fail. Applied once, before any mediapipe
import. Safe to call when protobuf is missing or already compatible.
"""

from __future__ import annotations

_APPLIED = False


def apply_protobuf_compat() -> bool:
    """Patch ``MessageFactory.GetPrototype`` when the method is missing.

    Returns True if GetPrototype is available afterwards (native or
    patched), False if protobuf is absent or cannot be patched.
    """
    global _APPLIED
    try:
        from google.protobuf import message_factory
    except ImportError:
        return False

    factory_cls = getattr(message_factory, "MessageFactory", None)
    if factory_cls is None:
        return False

    if hasattr(factory_cls, "GetPrototype"):
        _APPLIED = True
        return True

    getter = getattr(factory_cls, "GetMessageClass", None)
    module_getter = getattr(message_factory, "GetMessageClass", None)
    if getter is None and module_getter is None:
        return False

    if getter is not None:
        def _get_prototype(self, descriptor):  # noqa: ANN001
            return getter(self, descriptor)
    else:
        def _get_prototype(self, descriptor):  # noqa: ANN001
            return module_getter(descriptor)

    factory_cls.GetPrototype = _get_prototype  # type: ignore[attr-defined]
    _APPLIED = True
    return True
