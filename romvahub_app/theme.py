"""Light and dark themes: one palette each, turned into a Qt style sheet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F5F6F8", "surface": "#FFFFFF", "side": "#FAFBFC", "border": "#E1E5EA", "text": "#111827",
    "muted": "#566070", "hover": "#F0F3F7", "sel": "#E8F0FF", "accent": "#2563EB", "accent_fg": "#FFFFFF",
    "ok": "#15803D", "ok_dot": "#22C55E", "off_dot": "#9AA3B2", "danger": "#B91C1C",
    "draft_bg": "#EDEFF2", "draft_fg": "#4B5563", "ready_bg": "#DFEBFF", "ready_fg": "#1D4ED8",
    "applied_bg": "#EDE7FF", "applied_fg": "#6D28D9", "interview_bg": "#FFEAD1", "interview_fg": "#B4410C",
    "offer_bg": "#D9F7E3", "offer_fg": "#15803D", "failed_bg": "#FDE3E3", "failed_fg": "#B91C1C",
    "log_bg": "#0F1115", "log_fg": "#D6DAE1",
}

DARK = {
    "bg": "#0F1115", "surface": "#171A21", "side": "#13161C", "border": "#2A2F3A", "text": "#E7E9ED",
    "muted": "#9EA7B5", "hover": "#1E222B", "sel": "#1A2742", "accent": "#2563EB", "accent_fg": "#FFFFFF",
    "ok": "#86EFAC", "ok_dot": "#22C55E", "off_dot": "#5B6472", "danger": "#FCA5A5",
    "draft_bg": "#262B35", "draft_fg": "#C7CDD7", "ready_bg": "#17284A", "ready_fg": "#9DBEFF",
    "applied_bg": "#291F48", "applied_fg": "#C9B6FF", "interview_bg": "#3A2414", "interview_fg": "#FDBA74",
    "offer_bg": "#11301E", "offer_fg": "#86EFAC", "failed_bg": "#3B1618", "failed_fg": "#FCA5A5",
    "log_bg": "#0B0D10", "log_fg": "#D6DAE1",
}

_current = dict(LIGHT)


def colors() -> dict:
    return _current


def chip_colors(kind: str) -> tuple[str, str]:
    c = _current
    return c.get(f"{kind}_bg", c["draft_bg"]), c.get(f"{kind}_fg", c["draft_fg"])


def resolve(choice: str) -> str:
    if choice == "system":
        hints = QGuiApplication.styleHints()
        try:
            return "dark" if hints.colorScheme() == Qt.ColorScheme.Dark else "light"
        except AttributeError:
            return "light"
    return "dark" if choice == "dark" else "light"


def apply(app: QApplication, choice: str) -> str:
    """Apply a theme ("light", "dark" or "system") to the whole app; returns the one used."""
    name = resolve(choice)
    _current.clear()
    _current.update(DARK if name == "dark" else LIGHT)
    c = _current
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["hover"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["surface"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["accent_fg"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["surface"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c))
    return name


def stylesheet(c: dict) -> str:
    return f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {c['text']}; }}
QMainWindow, QDialog, #Page {{ background: {c['bg']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}

#Sidebar {{ background: {c['side']}; border-right: 1px solid {c['border']}; }}
#Brand {{ font-size: 12pt; font-weight: 700; }}
#BrandMark {{ background: {c['accent']}; color: {c['accent_fg']}; border-radius: 8px; font-weight: 700; font-size: 13pt; }}
#NavButton {{ text-align: left; padding: 9px 12px; border: none; border-radius: 8px; background: transparent; font-weight: 500; }}
#NavButton:hover {{ background: {c['hover']}; }}
#NavButton:checked {{ background: {c['sel']}; color: {c['accent']}; font-weight: 600; }}
#NavSection {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; padding: 10px 12px 2px 12px; }}

#TopBar, #StatusBar {{ background: {c['surface']}; }}
#TopBar {{ border-bottom: 1px solid {c['border']}; }}
#StatusBar {{ border-top: 1px solid {c['border']}; }}

#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
#Title {{ font-size: 16pt; font-weight: 700; }}
#Subtitle, #Muted {{ color: {c['muted']}; }}
#Label {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; }}
#Big {{ font-size: 20pt; font-weight: 700; }}
#Error {{ color: {c['danger']}; }}
#Ok {{ color: {c['ok']}; font-weight: 600; }}

QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['hover']}; }}
QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_fg']}; border: 1px solid {c['accent']}; }}
QPushButton#Primary:hover {{ background: {c['ready_fg']}; }}
QPushButton#Primary:disabled {{ background: {c['draft_bg']}; color: {c['muted']}; border-color: {c['draft_bg']}; }}
QPushButton#Link {{ border: none; background: transparent; padding: 4px 6px; font-weight: 500; text-align: left; }}
QPushButton#Link:hover {{ text-decoration: underline; background: {c['hover']}; }}
QPushButton#Tab {{ border: 1px solid transparent; border-radius: 16px; padding: 6px 14px; background: transparent; color: {c['muted']}; }}
QPushButton#Tab:hover {{ background: {c['hover']}; color: {c['text']}; }}
QPushButton#Tab:checked {{ background: {c['surface']}; border-color: {c['border']}; color: {c['text']}; }}
QPushButton#Seg {{ border: none; border-radius: 7px; padding: 6px 14px; background: transparent; color: {c['muted']}; }}
QPushButton#Seg:checked {{ background: {c['surface']}; color: {c['text']}; }}
QPushButton#Page {{ padding: 5px 10px; min-width: 18px; }}
QPushButton#Page:checked {{ background: {c['accent']}; color: {c['accent_fg']}; border-color: {c['accent']}; }}
#TabBar, #SegBar {{ background: {c['hover']}; border-radius: 18px; }}
#SegBar {{ border-radius: 10px; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 10px; selection-background-color: {c['accent']}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; }}
QCheckBox {{ spacing: 8px; }}

QTableWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; gridline-color: transparent; }}
QTableWidget::item {{ border-bottom: 1px solid {c['border']}; padding: 4px; }}
QTableWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']}; padding: 8px 6px; font-size: 8pt; font-weight: 700; }}

QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['hover']}; color: {c['text']}; }}
QMenu::item:disabled {{ color: {c['muted']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}

QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; outline: none; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {c['hover']}; }}
QListWidget::item:selected {{ background: {c['sel']}; color: {c['accent']}; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; background: {c['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; border: none; color: {c['muted']}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}

#Toast {{ background: {c['text']}; color: {c['bg']}; border-radius: 10px; }}
#Toast QLabel {{ color: {c['bg']}; }}
#Toast QPushButton {{ color: {c['bg']}; background: transparent; border: none; text-decoration: underline; }}
#Banner {{ background: {c['interview_bg']}; border-radius: 8px; }}
#Banner QLabel {{ color: {c['interview_fg']}; font-weight: 600; }}
#Log {{ background: {c['log_bg']}; color: {c['log_fg']}; border: none; border-radius: 0; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9pt; }}
"""
