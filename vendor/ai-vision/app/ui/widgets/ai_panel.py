"""AI VISION chat panel (v1.4): history, input, quick commands, streaming.

Header shows the AI ASSISTANT status badge (READY / THINKING / OFFLINE /
MOCK — real provider state only). All LLM calls run in worker threads
(AIVisionEngine.ask_async); token chunks arrive via Qt signals
(auto-queued to the GUI thread), so the UI never blocks. Built-in
commands are answered deterministically from the vision data; free-form
queries go to the LLM provider. EN + DE commands stay supported.
"""

from __future__ import annotations

import html
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ai.commands import answer_command, match_command
from app.ai.memory import match_memory_command
from app.ai.reactions import match_watch_request
from app.ui.components import StatusBadge

#: Buttons shown in the quick-command grid (full command set is still
#: matched from typed text).
QUICK_COMMANDS: tuple[str, ...] = (
    "WHAT IS MOVING?",
    "ARM STATE?",
    "DESCRIBE PERSON",
    "ANALYZE IMAGE",
    "COMPARE IMAGES",
    "WHAT CHANGED?",
    "CAPTURE SCENE",
    "GENERATE FROM SCENE",
    "VISION SUMMARY",
)

#: Commands routed to the (synchronous) vision intent handler.
INTENT_COMMANDS: tuple[str, ...] = (
    "ANALYZE IMAGE",
    "COMPARE IMAGES",
    "IMPROVE IMAGE",
    "GENERATE VARIANT",
    "WHAT CHANGED?",
    "CAPTURE AND GENERATE",
    "SESSION RECAP",
    "START RECORDING",
    "STOP RECORDING",
    "TAKE SNAPSHOT",
)
from app.ai.engine import AIVisionEngine
from app.core.types import SceneSnapshot
from app.utils.logging_setup import get_logger

log = get_logger("ui.ai_panel")

def _chat_colors() -> dict[str, str]:
    """Theme-aware chat palette (re-read on every render — cheap)."""
    from app.ui.theme import palette

    tokens = palette()
    return {
        "user": tokens.get("accent", "#00d9ff"),
        "ai": tokens.get("text", "#d8e2ea"),
        "event": tokens.get("muted", "#64788a"),
        "error": tokens.get("danger", "#ff5d5d"),
        "system": tokens.get("warn", "#ffb454"),
    }


class _Bridge(QObject):
    """Signal bridge: worker-thread callbacks -> GUI thread slots."""

    token = Signal(str)
    done = Signal(str)
    error = Signal(str)
    intent_done = Signal(str)


class AIPanel(QWidget):
    """Chat interface for the AI vision layer."""

    def __init__(
        self,
        engine: AIVisionEngine,
        snapshot_provider: Callable[[], Optional[SceneSnapshot]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._snapshot_provider = snapshot_provider
        self._blocks: list[tuple[str, str]] = []  # (kind, text)
        self._streaming = False
        # Optional handler for image-generation intents; runs in a worker
        # thread and returns a status message shown in the chat.
        self._image_intent_handler: Optional[Callable[[], str]] = None
        self._vision_intent_handler: Optional[Callable[[str], str]] = None
        self._watch_handler: Optional[Callable[[str], str]] = None
        # Voice (Phase 17/28): optional speak/listen handlers + capability state.
        self._speak_handler: Optional[Callable[[str], None]] = None
        self._listen_handler: Optional[Callable[[], None]] = None
        self._voice_status = "unavailable"
        self._stt_status = "unavailable"
        self._voice_auto = False
        # Session memory (Phase 22) — optional, bounded, RAM-only.
        self._memory = None
        self._bridge = _Bridge()
        self._bridge.token.connect(self._on_token)
        self._bridge.done.connect(self._on_done)
        self._bridge.error.connect(self._on_error)
        self._bridge.intent_done.connect(self._on_intent_done)

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("AI ASSISTANT")
        title.setObjectName("panel_title")
        header.addWidget(title)
        header.addStretch(1)
        # Hidden text label (compat for callers/tests); the badge is the
        # visible status indicator.
        self.status_label = QLabel("LLM: —")
        self.status_label.setObjectName("hint")
        self.status_label.setVisible(False)
        header.addWidget(self.status_label)
        self._status_badge = StatusBadge()
        self._status_badge.set_status("idle", "STATUS: —")
        header.addWidget(self._status_badge)
        header.addSpacing(8)
        self.speak_button = QPushButton("SPEAK")
        self.speak_button.setObjectName("ghost")
        self.speak_button.setVisible(False)
        self.speak_button.clicked.connect(self._on_speak_clicked)
        header.addWidget(self.speak_button)
        self.listen_button = QPushButton("LISTEN")
        self.listen_button.setObjectName("ghost")
        self.listen_button.setVisible(False)
        self.listen_button.clicked.connect(self._on_listen_clicked)
        header.addWidget(self.listen_button)
        self.clear_button = QPushButton("CLEAR CHAT")
        self.clear_button.setObjectName("ghost")
        self.clear_button.clicked.connect(self._on_clear)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        self.history = QTextBrowser()
        self.history.setOpenExternalLinks(False)
        self.history.setMinimumHeight(200)
        layout.addWidget(self.history, 1)

        commands_title = QLabel("QUICK COMMANDS")
        commands_title.setObjectName("panel_title")
        layout.addWidget(commands_title)

        grid = QGridLayout()
        grid.setSpacing(4)
        for index, command in enumerate(QUICK_COMMANDS):
            button = QPushButton(command)
            button.setStyleSheet(
                "QPushButton { padding: 5px 8px; font-size: 11px; }"
            )
            button.setToolTip(f"Run the '{command}' command.")
            button.setAccessibleName(f"Quick command: {command}")
            button.clicked.connect(
                lambda _checked=False, c=command: self.submit(c)
            )
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)

        self.state_label = QLabel("")
        self.state_label.setObjectName("hint")
        layout.addWidget(self.state_label)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about the scene… (EN or DE)")
        self.input.returnPressed.connect(self._on_send_clicked)
        input_row.addWidget(self.input, 1)
        self.stop_button = QPushButton("STOP")
        self.stop_button.setObjectName("danger")
        self.stop_button.setToolTip(
            "Abort the running LLM call (cooperative cancel)."
        )
        self.stop_button.setAccessibleName("Stop AI generation")
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        input_row.addWidget(self.stop_button)
        self.send_button = QPushButton("SEND")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        # Keyboard navigation: Ctrl+Enter sends, Ctrl+L clears the chat.
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_send_clicked)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._on_clear)

        self._render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_status(self, text: str, offline: bool = False) -> None:
        """Update the status badge (and the hidden text label used by
        tests). The badge shows READY / MOCK / OFFLINE — real state only."""
        self.status_label.setText(text)
        if offline:
            self._status_badge.set_status("offline", "OFFLINE")
        elif "MOCK" in text.upper():
            self._status_badge.set_status("mock", "MOCK")
        elif "ONLINE" in text.upper():
            self._status_badge.set_status("ready", "READY")
        else:
            self._status_badge.set_status("idle", "—")

    def _set_state_badge(self, status: str, text: str) -> None:
        self._status_badge.set_status(status, text)

    def set_memory(self, memory) -> None:
        """Wire the session memory (REMEMBER / RECALL / FORGET)."""
        self._memory = memory

    def set_extension_patterns(
        self, patterns: Optional[dict[str, tuple[str, ...]]]
    ) -> None:
        """Optional extra command aliases from local plugins."""
        self._extra_patterns = patterns or {}

    def set_extension_handler(
        self, handler: Optional[Callable[[str], Optional[str]]]
    ) -> None:
        """Optional plugin command dispatcher (returns None if unknown)."""
        self._extension_handler = handler

    def set_speak_handler(self, handler: Optional[Callable[[str], None]]) -> None:
        """Wire the local TTS engine (SPEAK + optional auto-speak)."""
        self._speak_handler = handler

    def set_listen_handler(self, handler: Optional[Callable[[], None]]) -> None:
        """Wire the local STT engine (LISTEN — one utterance)."""
        self._listen_handler = handler

    def set_stt_status(self, status: str, detail: str = "") -> None:
        """Capability-gate the LISTEN button (real | mock | unavailable)."""
        self._stt_status = status
        if status in ("real", "mock"):
            self.listen_button.setVisible(True)
            self.listen_button.setEnabled(True)
            self.listen_button.setToolTip(
                "Listen for one spoken command"
                + (f" · {detail}" if detail else "")
            )
        else:
            self.listen_button.setVisible(False)
            self.listen_button.setEnabled(False)
            self.listen_button.setToolTip(
                "No system speech recognizer on this machine."
            )

    def _on_listen_clicked(self) -> None:
        if self._listen_handler is None:
            return
        self.listen_button.setEnabled(False)
        self.state_label.setText("LISTENING…")
        self._listen_handler()

    def finish_listen(self, transcript: Optional[str]) -> None:
        """GUI-thread: re-enable LISTEN and optionally submit the text."""
        self.listen_button.setEnabled(self._stt_status in ("real", "mock"))
        self.state_label.setText("")
        if transcript:
            self.submit(transcript)
        else:
            self.append_system(
                "Nothing heard — speak a command, or type it instead."
            )

    def set_voice_status(self, status: str, detail: str = "") -> None:
        """Capability-gate the SPEAK button (real | mock | unavailable)."""
        self._voice_status = status
        if status in ("real", "mock"):
            self.speak_button.setVisible(True)
            self.speak_button.setEnabled(True)
            self.speak_button.setToolTip(
                "Speak the last answer aloud"
                + (f" · {detail}" if detail else "")
            )
        else:
            self.speak_button.setVisible(False)
            self.speak_button.setEnabled(False)
            self.speak_button.setToolTip(
                "No system voice available on this machine."
            )

    def set_voice_auto(self, enabled: bool) -> None:
        """Auto-speak every AI answer (user setting, capability-gated
        by the voice status — no sound without a detected voice)."""
        self._voice_auto = bool(enabled)

    def _on_speak_clicked(self) -> None:
        if self._speak_handler is None:
            return
        for kind, text in reversed(self._blocks):
            if kind == "ai" and text.strip():
                self._speak_handler(text)
                return
            if kind == "system" and text.strip():
                self._speak_handler(text)
                return

    def _maybe_auto_speak(self, text: str) -> None:
        if self._voice_auto and self._voice_status in ("real", "mock") \
                and self._speak_handler is not None and text.strip():
            self._speak_handler(text)

    def set_image_intent_handler(self, handler: Optional[Callable[[], str]]) -> None:
        """Wire the AI -> image generation intent (runs in a worker thread)."""
        self._image_intent_handler = handler

    def set_watch_handler(self, handler: Optional[Callable[[str], str]]) -> None:
        """Wire the deterministic scene watches (reaction engine)."""
        self._watch_handler = handler

    def set_vision_intent_handler(self, handler: Optional[Callable[[str], str]]) -> None:
        """Wire the synchronous image-analysis intents (ANALYZE, COMPARE,
        IMPROVE, VARIANT, WHAT CHANGED). Runs on the GUI thread — the
        handlers only trigger async work."""
        self._vision_intent_handler = handler

    def append_system(self, text: str) -> None:
        """Add a SYSTEM line (image intent results etc.)."""
        self._blocks.append(("system", text))
        if len(self._blocks) > 200:
            self._blocks = self._blocks[-200:]
        self._render()

    def _on_intent_done(self, message: str) -> None:
        self.append_system(message)
        self._maybe_auto_speak(message)
        self._streaming = False
        self.state_label.setText("")
        self.send_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self._set_state_badge("ready", "READY")

    def append_event(self, text: str) -> None:
        """Add a gray [EVENT] line (scene change notifications)."""
        self._blocks.append(("event", text))
        if len(self._blocks) > 200:
            self._blocks = self._blocks[-200:]
        self._render()

    def submit(self, query: str) -> None:
        """Handle one user query (built-in command or LLM call)."""
        query = query.strip()
        if not query or self._streaming:
            return
        snapshot = self._snapshot_provider()

        self._blocks.append(("user", query))
        self._render()

        if self._memory is not None:
            memory_command, payload = match_memory_command(query)
            if memory_command is not None:
                answer = self._memory.answer(memory_command, payload)
                self._blocks.append(("system", answer))
                self._render()
                return

        if self._watch_handler is not None:
            watch_target = match_watch_request(query)
            if watch_target is not None:
                try:
                    message = self._watch_handler(watch_target)
                except Exception as exc:  # noqa: BLE001 — readable chat message
                    message = f"Watch failed: {exc}"
                self._blocks.append(("system", message))
                self._render()
                return

        extras = getattr(self, "_extra_patterns", None)
        command = match_command(query, extra=extras)
        extension_handler = getattr(self, "_extension_handler", None)
        if command is not None and extension_handler is not None:
            extra_answer = extension_handler(command)
            if extra_answer is not None:
                self._blocks.append(("system", extra_answer))
                self._render()
                return
        if command in INTENT_COMMANDS:
            if self._vision_intent_handler is None:
                self._blocks.append(
                    ("ai", f"Command '{command}' is not available here.")
                )
            else:
                try:
                    message = self._vision_intent_handler(command)
                except Exception as exc:  # noqa: BLE001 — readable chat message
                    message = f"Command failed: {exc}"
                self._blocks.append(("system", message))
            self._render()
            return
        if command == "CREATE SCENE IMAGE":
            if self._image_intent_handler is None:
                self._blocks.append(
                    ("ai", "Image generation is not available right now.")
                )
                self._render()
                return
            self._streaming = True
            self.state_label.setText("PREPARING IMAGE…")
            self._set_state_badge("processing", "PROCESSING")
            self.send_button.setEnabled(False)
            # No STOP here: the enqueue itself is instant and cannot be
            # cancelled via cancel_current() — showing a STOP button
            # that does nothing would be a fake control. Only real LLM
            # streams get the STOP button.
            self.stop_button.setVisible(False)

            def _work() -> None:
                try:
                    message = self._image_intent_handler()
                except Exception as exc:  # noqa: BLE001 — readable chat message
                    message = f"Image generation failed: {exc}"
                self._bridge.intent_done.emit(message)

            threading.Thread(
                target=_work, name="ai-image-intent", daemon=True
            ).start()
            return
        if command is not None:
            answer = answer_command(command, snapshot)
            self._blocks.append(("ai", answer))
            self._render()
            return

        # Free-form query -> LLM (worker thread).
        self._blocks.append(("ai", ""))
        self._streaming = True
        self.state_label.setText("THINKING…")
        self._set_state_badge("processing", "THINKING")
        self.send_button.setEnabled(False)
        self.stop_button.setVisible(True)
        memory_context = ""
        if self._memory is not None:
            memory_context = self._memory.context_block()
        self._engine.ask_async(
            query,
            snapshot,
            on_token=self._bridge.token.emit,
            on_done=self._bridge.done.emit,
            on_error=self._bridge.error.emit,
            memory_context=memory_context,
        )

    # ------------------------------------------------------------------
    # Streaming slots (GUI thread)
    # ------------------------------------------------------------------
    def _on_token(self, token: str) -> None:
        if self._blocks and self._blocks[-1][0] == "ai":
            kind, text = self._blocks[-1]
            self._blocks[-1] = (kind, text + token)
            self._render()

    def _on_done(self, full_text: str) -> None:
        self._streaming = False
        self.state_label.setText("")
        self.send_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self._set_state_badge("ready", "READY")
        self._render()
        self._maybe_auto_speak(full_text)

    def _on_error(self, message: str) -> None:
        if self._blocks and self._blocks[-1][0] == "ai" and not self._blocks[-1][1]:
            self._blocks.pop()
        if str(message).strip() == "cancelled":
            # Cooperative STOP: keep the partial text, note the cancel.
            self._blocks.append(("system", "Request cancelled."))
            self._streaming = False
            self.state_label.setText("")
            self.send_button.setEnabled(True)
            self.stop_button.setVisible(False)
            self._set_state_badge("ready", "READY")
            self._render()
            return
        # WHAT/WHY/HOW TO FIX contract — never a raw provider error.
        from app.ui.errors import split_llm_error

        what, why, fix, details = split_llm_error(message)
        lines = [what, f"WHY: {why}", f"HOW TO FIX: {fix}"]
        if details:
            lines.append(f"DETAILS: {details[:200]}")
        self._blocks.append(("error", "\n".join(lines)))
        self._streaming = False
        self.state_label.setText("")
        self.send_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self._set_state_badge("offline", "OFFLINE")
        self._render()

    def _on_send_clicked(self) -> None:
        self.submit(self.input.text())
        self.input.clear()

    def _on_stop_clicked(self) -> None:
        """Abort the running LLM call (cooperative cancel via the engine)."""
        if self._streaming:
            self._engine.cancel_current()
            self.state_label.setText("CANCELLING…")

    def _on_clear(self) -> None:
        self._blocks.clear()
        self._engine.clear_chat()
        self._render()

    # ------------------------------------------------------------------
    def _render(self) -> None:
        parts: list[str] = ["<html><body style='font-size:12px;'>"]
        colors = _chat_colors()
        for kind, text in self._blocks:
            color = colors.get(kind, colors["ai"])
            if kind == "user":
                prefix = "<b>YOU</b>"
            elif kind == "event":
                prefix = "<b>EVENT</b>"
            elif kind == "error":
                prefix = "<b>AI</b>"
            elif kind == "system":
                prefix = "<b>SYSTEM</b>"
            else:
                prefix = "<b>AI</b>"
            escaped = html.escape(text).replace(chr(10), "<br>")
            parts.append(
                f"<p style='color:{color}; margin:6px 0;'>"
                f"<span style='font-size:9px; letter-spacing:2px;'>"
                f"{prefix}</span><br>{escaped}</p>"
            )
        parts.append("</body></html>")
        self.history.setHtml("".join(parts))
        scrollbar = self.history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def apply_palette(self) -> None:
        """Re-render with the active theme's colors (theme toggle)."""
        self._render()
