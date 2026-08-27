"""Global command center (Ctrl+K) — professional command palette (v1.4).

A searchable palette of application actions grouped into categories
(NAVIGATION / VISION / IMAGE / AI / SYSTEM) with full keyboard
navigation (type to filter, Up/Down to select, Enter to run, Esc to
close) and visible shortcuts. Actions are wired by the MainWindow —
the palette itself is a pure UI component. Opens with a subtle fade;
the effect runs on the GUI thread only.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

CommandAction = tuple[str, str, Callable[[], None]]  # (id, label, action)

#: V2 entries: (category, id, label, shortcut, action).
CommandEntry = tuple[str, str, str, str, Callable[[], None]]

_CATEGORIES = ("NAVIGATION", "VISION", "IMAGE", "AI", "SYSTEM")


class CommandCenter(QFrame):
    """Overlay palette listing and executing application actions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("commandCenter")
        self.setFixedSize(560, 420)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("COMMAND CENTER")
        title.setObjectName("panel_title")
        header.addWidget(title)
        header.addStretch(1)
        shortcut_hint = QLabel("CTRL+K")
        shortcut_hint.setObjectName("commandShortcut")
        header.addWidget(shortcut_hint)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search commands…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.list_widget, 1)

        hint = QLabel("↑↓ select · Enter run · Esc close")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        #: flat actions for compatibility: [(id, label, callable), ...]
        self._actions: list[CommandAction] = []
        #: v2 entries: [(category, id, label, shortcut, callable), ...]
        self._entries: list[CommandEntry] = []

        self.shortcut = QShortcut(QKeySequence("Ctrl+K"), self.parentWidget()
                                  if self.parentWidget() else self)
        self.shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut.activated.connect(self.toggle)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(140)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------------
    def set_actions(self, actions: list[CommandAction]) -> None:
        """Replace the command list (flat, uncategorized compatibility API)."""
        self._actions = actions
        self._entries = [
            ("", action_id, label, "", action)
            for action_id, label, action in actions
        ]
        self._filter("")

    def set_actions_v2(self, entries: list[CommandEntry]) -> None:
        """Replace the command list with categorized entries."""
        self._entries = entries
        self._actions = [
            (action_id, label, action)
            for _category, action_id, label, _shortcut, action in entries
        ]
        self._filter("")

    # ------------------------------------------------------------------
    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        self.list_widget.clear()
        current_category: Optional[str] = None
        for category, action_id, label, shortcut, _action in self._entries:
            if query and (
                query not in label.lower() and query not in action_id.lower()
                and query not in shortcut.lower()
            ):
                continue
            # Category headers only in browse mode (professional palette
            # behavior: filtering shows a flat result list).
            if category and not query and category != current_category:
                self._add_category_row(category)
                current_category = category
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, action_id)
            item.setSizeHint(self._row_size_hint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(
                item, self._action_row(label, shortcut)
            )
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _add_category_row(self, category: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, f"__category__{category}")
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable
        item.setSizeHint(self._row_size_hint())
        self.list_widget.addItem(item)
        label = QLabel(category)
        label.setObjectName("commandCategory")
        self.list_widget.setItemWidget(item, label)

    def _action_row(self, label: str, shortcut: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(8)
        name = QLabel(label)
        layout.addWidget(name, 1)
        if shortcut:
            hint = QLabel(shortcut)
            hint.setObjectName("commandShortcut")
            layout.addWidget(hint)
        return row

    def _row_size_hint(self):
        from PySide6.QtCore import QSize

        return QSize(0, 30)

    # ------------------------------------------------------------------
    def _run_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        action_id = item.data(Qt.ItemDataRole.UserRole)
        for candidate_id, _label, action in self._actions:
            if candidate_id == action_id:
                self.close_palette()
                action()
                return

    # ------------------------------------------------------------------
    def open_palette(self) -> None:
        self.search.clear()
        self._filter("")
        self.move_to_center()
        self.show()
        self.raise_()
        self._opacity.setOpacity(0.0)
        self._fade_in.start()
        self.search.setFocus()

    def close_palette(self) -> None:
        self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.close_palette()
        else:
            self.open_palette()

    def move_to_center(self) -> None:
        if self.parentWidget() is not None:
            parent = self.parentWidget()
            self.move(
                (parent.width() - self.width()) // 2,
                (parent.height() - self.height()) // 3,
            )

    # ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt API
        if event.key() == Qt.Key.Key_Escape:
            self.close_palette()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._run_current()
            return
        if event.key() == Qt.Key.Key_Down:
            self._move_selection(1)
            return
        if event.key() == Qt.Key.Key_Up:
            self._move_selection(-1)
            return
        super().keyPressEvent(event)

    def _move_selection(self, delta: int) -> None:
        """Move the selection, skipping non-selectable category rows."""
        count = self.list_widget.count()
        if count == 0:
            return
        row = self.list_widget.currentRow()
        for _ in range(count):
            row = (row + delta) % count
            item = self.list_widget.item(row)
            if item is not None and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.list_widget.setCurrentRow(row)
                return

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self.isVisible():
            self.move_to_center()
        super().resizeEvent(event)
