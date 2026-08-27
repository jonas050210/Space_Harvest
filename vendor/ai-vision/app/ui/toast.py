"""Toast notifications (v1.4) — professional, structured, honest.

Transient messages in the bottom-right corner of the main window.
Success/info toasts show a title + one body line. Error toasts are
structured exactly like the rest of the product's error handling:

    WHAT      — what happened (one line)
    WHY       — why it happened (one line)
    HOW TO FIX — what the user can do (one line)
    DETAILS   — technical detail, only in the tooltip (never a raw
                Python/HTTP error in the visible text)

Auto-dismiss after a few seconds with a fade; all animation runs on the
GUI thread via Qt and never touches the vision worker.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import status_color

#: (kind -> status name for coloring)
_KIND_STATUS = {
    "info": "processing",
    "success": "ready",
    "warning": "mock",
    "error": "error",
}

#: (kind -> default title word)
_KIND_TITLE = {
    "info": "NOTICE",
    "success": "COMPLETE",
    "warning": "ATTENTION",
    "error": "FAILED",
}

_DISPLAY_MS = 4000
_ERROR_DISPLAY_MS = 8000
_FADE_MS = 350
_MAX_TOASTS = 4


class Toast(QFrame):
    """One toast message (title + optional body block)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFixedWidth(360)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 12)
        self._layout.setSpacing(4)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade.finished.connect(self.hide)

    # ------------------------------------------------------------------
    def _add_title(self, text: str, color: str) -> None:
        title = QLabel(text.upper())
        title.setObjectName("toastTitle")
        title.setStyleSheet(f"color: {color};")
        self._layout.addWidget(title)

    def _add_body(self, text: str) -> None:
        body = QLabel(text)
        body.setObjectName("toastBody")
        body.setWordWrap(True)
        self._layout.addWidget(body)

    def _add_row(self, key: str, text: str) -> None:
        row = QVBoxLayout()
        row.setSpacing(0)
        label = QLabel(key)
        label.setObjectName("toastKey")
        row.addWidget(label)
        value = QLabel(text)
        value.setObjectName("toastBody")
        value.setWordWrap(True)
        row.addWidget(value)
        self._layout.addLayout(row)

    # ------------------------------------------------------------------
    @classmethod
    def simple(cls, text: str, kind: str, parent=None) -> "Toast":
        toast = cls(parent)
        color = status_color(_KIND_STATUS.get(kind, "processing"))
        toast._add_title(_KIND_TITLE.get(kind, "NOTICE"), color)
        toast._add_body(text)
        toast.setToolTip("")
        return toast

    @classmethod
    def structured(
        cls,
        what: str,
        why: str,
        fix: str,
        details: str = "",
        parent=None,
    ) -> "Toast":
        """Error toast with the WHAT / WHY / HOW TO FIX contract."""
        toast = cls(parent)
        color = status_color("error")
        toast._add_title("ERROR", color)
        toast._add_row("WHAT", what)
        toast._add_row("WHY", why)
        toast._add_row("HOW TO FIX", fix)
        if details:
            toast.setToolTip(details[:400])
        return toast


class ToastManager(QWidget):
    """Stacks toasts bottom-right of the window; keeps at most N visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._toasts: list[Toast] = []
        self._timers: dict[Toast, QTimer] = {}

    # ------------------------------------------------------------------
    def notify(self, text: str, kind: str = "info") -> None:
        """Show a transient toast (called from the GUI thread)."""
        self._push(Toast.simple(text, kind, self), kind != "error")

    def notify_error(
        self, what: str, why: str = "", fix: str = "", details: str = ""
    ) -> None:
        """Structured error toast (WHAT / WHY / HOW TO FIX / DETAILS)."""
        self._push(
            Toast.structured(what, why, fix, details, self),
            long_lived=True,
        )

    def _push(self, toast: Toast, long_lived: bool = False) -> None:
        self._toasts.append(toast)
        toast.show()
        toast.raise_()

        # Enforce the visible maximum (oldest dropped instantly).
        while len(self._toasts) > _MAX_TOASTS:
            old = self._toasts.pop(0)
            timer = self._timers.pop(old, None)
            if timer is not None:
                timer.stop()
            old.deleteLater()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=toast: self._dismiss(t))
        self._timers[toast] = timer
        timer.start(_ERROR_DISPLAY_MS if long_lived else _DISPLAY_MS)
        self._reflow()

    def _dismiss(self, toast: Toast) -> None:
        self._timers.pop(toast, None)
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast._fade.start()

    def _reflow(self) -> None:
        if self.parentWidget() is None:
            return
        parent = self.parentWidget()
        y = parent.height() - 120
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height() + 8
            toast.move(parent.width() - toast.width() - 24, max(8, y))

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._reflow()
        super().resizeEvent(event)

    def close_toasts(self) -> None:
        for timer in list(self._timers.values()):
            timer.stop()
        self._timers.clear()
        for toast in self._toasts:
            toast.deleteLater()
        self._toasts.clear()
