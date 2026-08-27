"""Application theme — "command center" premium design system (v1.4).

Design language: deep layered dark surfaces, hairline borders, one cyan
accent, monospaced values, and a strict status palette. Status colors
carry meaning ONLY:

    LIVE          green     capture is running
    READY         green     verified and usable
    PROCESSING    cyan      work in progress
    OFFLINE       red       unreachable / error
    ERROR         red       failed
    CPU           gray      CPU delegate active
    GPU           green     GPU delegate active
    MOCK          amber     mock provider (clearly labeled)
    UNTESTABLE    violet    environment cannot verify

Every interactive element defines hover / active / disabled / focus
states. All effects are pure Qt stylesheets (no timers, no animations in
the theme itself) so vision performance is never affected.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Palette tokens
# ---------------------------------------------------------------------------
_DARK = {
    "bg": "#05080c",
    "panel": "#0b1118",
    "panel_alt": "#0f1721",
    "panel_hover": "#15222e",
    "border": "#1a2836",
    "border_strong": "#2a3f54",
    "text": "#dde7f0",
    "muted": "#64788a",
    "accent": "#00d9ff",
    "accent_dim": "#0c3340",
    "accent_text": "#042029",
    "success": "#2bd97c",
    "danger": "#ff5d5d",
    "warn": "#ffb454",
    "untestable": "#a78bfa",
    "video": "#04070a",
}

_LIGHT = {
    "bg": "#eef2f6",
    "panel": "#ffffff",
    "panel_alt": "#f3f6f9",
    "panel_hover": "#e9eef3",
    "border": "#cdd8e1",
    "border_strong": "#aebdca",
    "text": "#18222e",
    "muted": "#5c6c7c",
    "accent": "#008fb3",
    "accent_dim": "#d4eef6",
    "accent_text": "#ffffff",
    "success": "#1c9d62",
    "danger": "#d43b3b",
    "warn": "#c07a1d",
    "untestable": "#6d4fd1",
    "video": "#10161d",
}

_FONT_UI = "'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif"
_FONT_MONO = "'JetBrains Mono', 'Cascadia Mono', Consolas, 'Courier New', monospace"

#: Currently applied tokens (set by :func:`apply_theme`). Widgets read
#: programmatic colors from here so every UI element follows the theme.
_ACTIVE: dict[str, str] = dict(_DARK)

#: Semantic status -> palette token (meaning only, never decoration).
_SEMANTIC_TOKENS = {
    "live": "success",
    "ready": "success",
    "processing": "accent",
    "offline": "danger",
    "error": "danger",
    "cpu": "muted",
    "gpu": "success",
    "mock": "warn",
    "untestable": "untestable",
    # legacy aliases
    "running": "accent",
    "idle": "muted",
    "unknown": "muted",
    "success": "success",
    "warning": "warn",
}


def palette() -> dict[str, str]:
    """The active theme's color tokens (e.g. ``palette()['muted']``)."""
    return dict(_ACTIVE)


def is_dark() -> bool:
    """True while the dark theme is applied."""
    return _ACTIVE is _DARK


def semantic_color(kind: str) -> str:
    """Resolve a semantic status ('live', 'error', 'mock', ...) to the
    active theme's color. Unknown kinds resolve to ``muted``."""
    token = _SEMANTIC_TOKENS.get(kind.lower(), "muted")
    return _ACTIVE.get(token, _DARK.get(token, "#64788a"))


def _build_stylesheet(c: dict[str, str]) -> str:
    return f"""
* {{
    font-family: {_FONT_UI};
    font-size: 13px;
    color: {c['text']};
}}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget {{ background: transparent; }}
QToolTip {{
    background: {c['panel_alt']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ---------------- Panels ---------------- */
QFrame#panel {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#panel:hover {{ border-color: {c['border_strong']}; }}
QFrame#panelGlass {{
    background: rgba(11, 17, 24, 235);
    border: 1px solid {c['border_strong']};
    border-radius: 12px;
}}
QFrame#header {{
    background: {c['panel']};
    border-bottom: 1px solid {c['border']};
}}
QFrame#statusbar {{
    background: {c['panel']};
    border-top: 1px solid {c['border']};
}}
QFrame#calibrationOverlay {{ background: rgba(5, 8, 12, 242); }}
QFrame#sectionHeader {{ border-bottom: 1px solid {c['border']}; }}

/* ---------------- Typography ---------------- */
QLabel#h1 {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 4px;
    color: {c['text']};
}}
QLabel#panel_title {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {c['accent']};
}}
QLabel#value {{
    font-family: {_FONT_MONO};
    font-size: 14px;
    font-weight: 600;
    color: {c['text']};
}}
QLabel#value_dim {{
    font-family: {_FONT_MONO};
    font-size: 12px;
    color: {c['muted']};
}}
QLabel#hint {{ color: {c['muted']}; font-size: 11px; }}
QLabel#error_hint {{ color: {c['danger']}; font-size: 11px; }}
QLabel#live {{
    font-family: {_FONT_MONO};
    font-weight: 700;
    letter-spacing: 2px;
    font-size: 13px;
    color: {c['success']};
}}
QLabel#live_off {{
    font-family: {_FONT_MONO};
    font-weight: 700;
    letter-spacing: 2px;
    font-size: 13px;
    color: {c['muted']};
}}
QLabel#kpi_label {{
    color: {c['muted']};
    font-size: 10px;
    letter-spacing: 1px;
}}
QLabel#pageTitle {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 1px;
    color: {c['text']};
}}
QLabel#pageSubtitle {{ color: {c['muted']}; font-size: 12px; }}
QLabel#heroTitle {{
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 6px;
    color: {c['text']};
}}
QLabel#brandAccent {{ color: {c['accent']}; }}

/* ---------------- Buttons ---------------- */
QPushButton {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 1px;
    color: {c['text']};
}}
QPushButton:hover {{
    border-color: {c['border_strong']};
    background: {c['panel_hover']};
}}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{
    color: {c['muted']};
    background: {c['panel']};
    border-color: {c['border']};
}}
QPushButton#primary {{
    background: {c['accent_dim']};
    border: 1px solid {c['accent']};
    color: {c['accent']};
}}
QPushButton#primary:hover {{ background: {c['accent']}; color: {c['accent_text']}; }}
QPushButton#primary:disabled {{
    background: {c['panel']};
    border-color: {c['border']};
    color: {c['muted']};
}}
QPushButton#danger {{
    background: {c['panel_alt']};
    border: 1px solid {c['danger']};
    color: {c['danger']};
}}
QPushButton#danger:hover {{ background: {c['danger']}; color: #2b0606; }}
QPushButton#danger:disabled {{
    background: {c['panel']};
    border-color: {c['border']};
    color: {c['muted']};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {c['muted']};
}}
QPushButton#ghost:hover {{
    border-color: {c['border_strong']};
    color: {c['text']};
}}
QPushButton:focus {{ border-color: {c['accent']}; }}

/* ---------------- Inputs ---------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextBrowser {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 6px 10px;
    selection-background-color: {c['accent_dim']};
    selection-color: {c['text']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextBrowser:focus {{ border-color: {c['border_strong']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {c['muted']};
    background: {c['panel']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['panel_alt']};
    border: 1px solid {c['border_strong']};
    border-radius: 7px;
    selection-background-color: {c['accent_dim']};
    selection-color: {c['text']};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px; border: none; background: {c['panel_alt']};
}}

/* ---------------- Switches ---------------- */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 34px; height: 18px;
    border-radius: 9px;
    border: 1px solid {c['border_strong']};
    background: {c['panel_alt']};
}}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{
    background: {c['accent_dim']};
    border-color: {c['accent']};
}}
QCheckBox::indicator:disabled {{ border-color: {c['border']}; }}

/* ---------------- Tabs ---------------- */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: {c['panel_alt']};
    color: {c['muted']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 6px 14px;
    margin-right: 4px;
    font-weight: 600;
    letter-spacing: 1px;
    font-size: 11px;
}}
QTabBar::tab:hover {{ color: {c['text']}; border-color: {c['border_strong']}; }}
QTabBar::tab:selected {{
    color: {c['accent']};
    border-color: {c['accent']};
    background: {c['accent_dim']};
}}

/* ---------------- Lists ---------------- */
QListWidget {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{
    border-radius: 6px;
    padding: 4px;
    color: {c['text']};
}}
QListWidget::item:hover {{ background: {c['panel_hover']}; }}
QListWidget::item:selected {{
    background: {c['accent_dim']};
    border: 1px solid {c['accent']};
}}
QListWidget::item:disabled {{ color: {c['muted']}; }}

/* ---------------- Sliders ---------------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c['border']};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {c['text']};
    border: 2px solid {c['accent']};
}}
QSlider::handle:horizontal:hover {{ background: {c['accent']}; }}

/* ---------------- Scrollbars ---------------- */
QScrollBar:vertical {{ background: transparent; width: 8px; border: none; }}
QScrollBar::handle:vertical {{
    background: {c['border_strong']}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; border: none; }}
QScrollBar::handle:horizontal {{
    background: {c['border_strong']}; border-radius: 4px; min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------------- Scroll areas ---------------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---------------- Progress (indeterminate) ---------------- */
QProgressBar {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: {c['text']};
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}

/* ---------------- Splitter + dialogs ---------------- */
QSplitter::handle {{ background: {c['bg']}; width: 6px; }}
QSplitter::handle:hover {{ background: {c['border_strong']}; }}
QMessageBox {{ background: {c['panel']}; }}
QMessageBox QPushButton {{ min-width: 80px; }}

/* ---------------- Navigation rail ---------------- */
QFrame#navRail {{
    background: {c['panel']};
    border-right: 1px solid {c['border']};
    border-radius: 0 10px 10px 0;
}}
QPushButton[nav="true"] {{
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 0;
    padding: 9px 12px;
    text-align: left;
    color: {c['muted']};
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 1px;
}}
QPushButton[nav="true"]:hover {{
    background: {c['panel_hover']};
    color: {c['text']};
}}
QPushButton[nav="true"]:checked {{
    color: {c['accent']};
    border-left: 2px solid {c['accent']};
    background: {c['accent_dim']};
}}

/* ---------------- Toasts ---------------- */
QFrame#toast {{
    background: rgba(13, 20, 28, 244);
    border: 1px solid {c['border_strong']};
    border-radius: 10px;
}}
QLabel#toastTitle {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#toastBody {{ color: {c['text']}; font-size: 12px; }}
QLabel#toastKey {{
    color: {c['muted']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}

/* ---------------- Command center ---------------- */
QFrame#commandCenter {{
    background: rgba(9, 15, 22, 248);
    border: 1px solid {c['accent']};
    border-radius: 14px;
}}
QFrame#commandCenter QListWidget {{
    background: transparent;
    border: none;
}}
QFrame#commandCenter QListWidget::item {{
    padding: 6px 10px;
    border-radius: 6px;
}}
QFrame#commandCenter QListWidget::item:selected {{
    background: {c['accent_dim']};
    color: {c['accent']};
}}
QLabel#commandCategory {{
    color: {c['muted']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#commandShortcut {{
    font-family: {_FONT_MONO};
    color: {c['muted']};
    font-size: 11px;
}}

/* ---------------- Collapsible sections ---------------- */
QPushButton#collapseToggle {{
    background: transparent;
    border: none;
    padding: 4px 6px;
    color: {c['accent']};
    font-weight: 700;
    letter-spacing: 1px;
    font-size: 10px;
}}
QPushButton#collapseToggle:hover {{ color: {c['text']}; }}

/* ---------------- Live HUD (video overlay) ---------------- */
QFrame#hud {{
    background: rgba(5, 8, 12, 205);
    border: 1px solid {c['border_strong']};
    border-radius: 9px;
}}
QLabel#hudCell {{
    font-family: {_FONT_MONO};
    font-size: 11px;
    font-weight: 600;
    color: {c['text']};
}}
QLabel#hudKey {{
    font-family: {_FONT_MONO};
    font-size: 9px;
    letter-spacing: 1px;
    color: {c['muted']};
}}

/* ---------------- Demo overlay ---------------- */
QFrame#demoOverlay {{
    background: rgba(9, 15, 22, 240);
    border: 1px solid {c['border_strong']};
    border-radius: 12px;
}}

/* Focus visibility (accessibility): outline on keyboard focus only is
   approximated with a clear border on focus for interactive widgets. */
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus {{
    outline: none;
}}
"""


def build_stylesheet(dark: bool) -> str:
    """Return the raw stylesheet text for the given mode (testable)."""
    tokens = _DARK if dark else _LIGHT
    return _build_stylesheet(tokens)


def apply_theme(app: QApplication, dark: bool) -> None:
    """Apply the stylesheet and a matching native palette."""
    global _ACTIVE
    tokens = _DARK if dark else _LIGHT
    _ACTIVE = tokens
    app.setStyleSheet(_build_stylesheet(tokens))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens["panel"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens["panel_alt"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["panel"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens["panel_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens["accent_dim"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens["muted"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens["panel_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens["text"]))
    app.setPalette(palette)
