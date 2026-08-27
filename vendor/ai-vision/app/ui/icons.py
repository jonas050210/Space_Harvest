"""Consistent icon system for the UI.

Uses Qt's standard icon set (native, theme-aware, no external assets,
no random Unicode glyphs) with a safe fallback: if an icon cannot be
resolved, the button keeps its text label instead of showing an empty
square. Status dots (●/○) remain text-based semantic indicators and are
not part of the icon system.
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QStyle


def apply_icon(button: QPushButton, standard_pixmap: QStyle.StandardPixmap,
               tooltip: str = "") -> None:
    """Set a standard icon on a button; keeps the text as fallback."""
    style = button.style()
    if style is None:
        return
    icon = style.standardIcon(standard_pixmap)
    if icon.isNull():
        # Fallback: keep whatever text the button already has.
        return
    button.setIcon(icon)
    if button.text() == "":
        button.setToolTip(tooltip)


def refresh_icon(button: QPushButton, tooltip: str = "Refresh") -> None:
    apply_icon(button, QStyle.StandardPixmap.SP_BrowserReload, tooltip)
