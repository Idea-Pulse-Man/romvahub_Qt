"""Light and dark themes: the mockup's colour tokens, turned into one Qt style sheet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4F5BD5"

LIGHT = {
    "name": "light",
    "bg": "#F5F6F8", "surface": "#FFFFFF", "side": "#FAFBFC", "border": "#E1E5EA", "border_strong": "#CDD3DB",
    "text": "#111827", "muted": "#5B6472", "faint": "#8A93A1", "hover": "#F0F3F7", "sel": "#EEF0FF",
    "accent": ACCENT, "accent_hover": "#4350C4", "accent_fg": "#FFFFFF", "accent_soft": "#E7E9FC",
    "ok": "#15803D", "ok_dot": "#22C55E", "off_dot": "#9AA3B2", "danger": "#B91C1C",
    "online_bg": "#DCF5E5", "online_fg": "#15803D",
    "draft_bg": "#EDEFF2", "draft_fg": "#4B5563", "ready_bg": "#E4E7FC", "ready_fg": "#3F4BC2",
    "applied_bg": "#EDE7FF", "applied_fg": "#6D28D9", "interview_bg": "#FFEAD1", "interview_fg": "#B4410C",
    "offer_bg": "#D9F7E3", "offer_fg": "#15803D", "failed_bg": "#FDE3E3", "failed_fg": "#B91C1C",
    "disabled_bg": "#EDEFF2", "disabled_fg": "#8A93A1",
    "log_bg": "#0F1115", "log_fg": "#D6DAE1", "avatar_bg": "#EDE7FF", "avatar_fg": "#6D28D9",
}

DARK = {
    "name": "dark",
    "bg": "#0F1115", "surface": "#171A21", "side": "#13161C", "border": "#2A2F3A", "border_strong": "#363C49",
    "text": "#E7E9ED", "muted": "#9EA7B5", "faint": "#6E7786", "hover": "#1E222B", "sel": "#1D2240",
    "accent": ACCENT, "accent_hover": "#5D69E0", "accent_fg": "#FFFFFF", "accent_soft": "#232A55",
    "ok": "#86EFAC", "ok_dot": "#22C55E", "off_dot": "#5B6472", "danger": "#FCA5A5",
    "online_bg": "#123222", "online_fg": "#86EFAC",
    "draft_bg": "#262B35", "draft_fg": "#C7CDD7", "ready_bg": "#232A55", "ready_fg": "#AEB6FF",
    "applied_bg": "#291F48", "applied_fg": "#C9B6FF", "interview_bg": "#3A2414", "interview_fg": "#FDBA74",
    "offer_bg": "#11301E", "offer_fg": "#86EFAC", "failed_bg": "#3B1618", "failed_fg": "#FCA5A5",
    "disabled_bg": "#22262F", "disabled_fg": "#6E7786",
    "log_bg": "#0B0D10", "log_fg": "#D6DAE1", "avatar_bg": "#291F48", "avatar_fg": "#C9B6FF",
}

_current = dict(LIGHT)


def colors() -> dict:
    return _current


def chip_colors(kind: str) -> tuple[str, str]:
    c = _current
    return c.get(f"{kind}_bg", c["draft_bg"]), c.get(f"{kind}_fg", c["draft_fg"])


def resolve(choice: str) -> str:
    if choice == "system":
        try:
            return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
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
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "surface"),
                      (QPalette.AlternateBase, "hover"), (QPalette.Text, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.HighlightedText, "accent_fg"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "faint"), (QPalette.Link, "accent")):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["disabled_fg"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["disabled_fg"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c) + _checkbox_image(c))
    return name


def _checkbox_image(c: dict) -> str:
    """A white tick for checked boxes (style sheets need an image file)."""
    try:
        from .config import data_dir
        from .ui.icons import pixmap

        path = data_dir() / "check-white.png"
        if not path.exists():
            pixmap("check", "#FFFFFF", 14, 3.0).save(str(path))
        return f"\nQCheckBox::indicator:checked {{ image: url({path.as_posix()}); }}\n"
    except Exception:  # noqa: BLE001 - a plain filled box is fine too
        return ""


def stylesheet(c: dict) -> str:
    return f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; color: {c['text']}; outline: none; }}
QMainWindow, QDialog, #Page, #MainStack {{ background: {c['bg']}; }}
#Card QStackedWidget, #Card QStackedWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px 8px; border-radius: 6px; }}
QLabel {{ background: transparent; }}

/* Sidebar */
#Sidebar {{ background: {c['side']}; border-right: 1px solid {c['border']}; }}
#Brand {{ font-size: 12pt; font-weight: 700; }}
#BrandMark {{ background: {c['accent']}; color: {c['accent_fg']}; border-radius: 9px; font-weight: 700; font-size: 13pt; }}
#NavButton {{ text-align: left; padding: 9px 12px; border: none; border-radius: 8px; background: transparent; font-size: 10.5pt; font-weight: 500; color: {c['text']}; }}
#NavButton:hover {{ background: {c['hover']}; }}
#NavButton:checked {{ background: {c['sel']}; color: {c['accent']}; font-weight: 600; }}
#NavSection {{ color: {c['faint']}; font-size: 8pt; font-weight: 700; padding: 14px 12px 4px 12px; letter-spacing: 1px; }}
#ConnCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}

/* Top bar, status bar */
#TopBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
#StatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
#TopSearch {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 7px 12px 7px 34px; font-size: 10.5pt; }}
#TopSearch:focus {{ border: 1px solid {c['accent']}; }}
#OnlinePill {{ background: {c['online_bg']}; color: {c['online_fg']}; border-radius: 14px; padding: 5px 12px; font-weight: 600; font-size: 9pt; }}
#OfflinePill {{ background: {c['failed_bg']}; color: {c['failed_fg']}; border-radius: 14px; padding: 5px 12px; font-weight: 600; font-size: 9pt; }}
#Avatar {{ background: {c['avatar_bg']}; color: {c['avatar_fg']}; border-radius: 13px; font-size: 8pt; font-weight: 700; }}

/* Cards and text */
#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
#Title {{ font-size: 17pt; font-weight: 700; }}
#Subtitle, #Muted {{ color: {c['muted']}; }}
#Faint {{ color: {c['faint']}; font-size: 9pt; }}
#Label {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; letter-spacing: 0.5px; }}
#Big {{ font-size: 21pt; font-weight: 700; }}
#Error {{ color: {c['danger']}; }}
#Ok {{ color: {c['ok']}; font-weight: 600; }}
#Accent {{ color: {c['accent']}; font-weight: 600; }}
#Strong {{ font-weight: 600; }}

/* Buttons */
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 14px; font-weight: 600; color: {c['text']}; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['border_strong']}; }}
QPushButton:disabled {{ color: {c['disabled_fg']}; background: {c['disabled_bg']}; border-color: {c['disabled_bg']}; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_fg']}; border: 1px solid {c['accent']}; }}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {c['disabled_bg']}; color: {c['disabled_fg']}; border-color: {c['disabled_bg']}; }}
QPushButton#Ghost {{ border: none; background: transparent; padding: 6px 8px; }}
QPushButton#Ghost:hover {{ background: {c['hover']}; }}
QPushButton#IconButton {{ padding: 0; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; border-radius: 8px; }}
QPushButton#Link {{ border: none; background: transparent; padding: 4px 6px; font-weight: 600; text-align: left; }}
QPushButton#Link:hover {{ text-decoration: underline; background: {c['hover']}; }}
QPushButton#TextLink {{ border: none; background: transparent; padding: 0; font-weight: 500; color: {c['accent']}; text-decoration: underline; }}
QPushButton#Seg {{ border: none; border-radius: 7px; padding: 6px 14px; background: transparent; color: {c['muted']}; }}
QPushButton#Seg:hover {{ color: {c['text']}; }}
QPushButton#Seg:checked {{ background: {c['surface']}; color: {c['text']}; }}
QPushButton#Page {{ padding: 6px 12px; min-width: 14px; }}
QPushButton#Page:checked {{ background: {c['accent']}; color: {c['accent_fg']}; border-color: {c['accent']}; }}
#SegBar {{ background: {c['hover']}; border-radius: 10px; }}
#TabBar {{ background: {c['hover']}; border: 1px solid {c['border']}; border-radius: 20px; }}
#TabButton {{ border: 1px solid transparent; border-radius: 16px; background: transparent; padding: 0; }}
#TabButton:hover {{ background: {c['surface']}; }}
#TabButton:checked {{ background: {c['surface']}; border: 1px solid {c['border']}; }}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 10px; selection-background-color: {c['accent']}; selection-color: {c['accent_fg']}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; padding: 4px; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {c['border_strong']}; border-radius: 4px; background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url(none); }}

/* The applications table */
#TableCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QTableWidget {{ background: transparent; border: none; gridline-color: transparent; }}
QTableWidget::item {{ border-bottom: 1px solid {c['border']}; padding-left: 5px; }}
QTableWidget::item:hover {{ background: {c['hover']}; }}
QTableWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']}; padding: 10px 8px; font-size: 8pt; font-weight: 700; }}
QTableCornerButton::section {{ background: {c['surface']}; border: none; }}

/* Other lists, tabs, menus */
QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {c['hover']}; }}
QListWidget::item:selected {{ background: {c['sel']}; color: {c['accent']}; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; background: {c['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; border: none; color: {c['muted']}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 26px 8px 12px; border-radius: 6px; color: {c['text']}; }}
QMenu::item:selected {{ background: {c['hover']}; }}
QMenu::item:disabled {{ color: {c['faint']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}

/* Profiles: cards and the editor's section cards */
#ProfileCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
#ProfileCard:hover {{ border-color: {c['border_strong']}; }}
#NewCard {{ background: transparent; border: 2px dashed {c['border_strong']}; border-radius: 14px; }}
#NewCard:hover {{ border-color: {c['accent']}; }}
#PlusBubble, #IconBubble {{ background: {c['accent_soft']}; border-radius: 17px; }}
#PlusBubble {{ border-radius: 24px; }}
#CardName {{ font-size: 11.5pt; font-weight: 700; }}
#SectionTitle {{ font-size: 13pt; font-weight: 700; }}
#FieldLabel {{ font-weight: 600; font-size: 9.5pt; }}
#Section {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
#Entry {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QProgressBar#Completion {{ background: {c['hover']}; border: none; border-radius: 3px; }}
QProgressBar#Completion::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QPushButton#RoundButton {{ padding: 0; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; border-radius: 14px; border: 1px dashed {c['border_strong']}; background: transparent; }}
QPushButton#RoundButton:hover {{ border-color: {c['accent']}; }}
QTabWidget#LineTabs::pane {{ border: none; border-top: 1px solid {c['border']}; background: transparent; }}
QTabWidget#LineTabs QTabBar {{ qproperty-drawBase: 0; border-bottom: 1px solid {c['border']}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}

#Toast {{ background: {c['text']}; border-radius: 10px; }}
#Toast QLabel {{ color: {c['bg']}; }}
#Toast QPushButton {{ color: {c['bg']}; background: transparent; border: none; text-decoration: underline; }}
#Banner {{ background: {c['interview_bg']}; border-radius: 8px; }}
#Banner QLabel {{ color: {c['interview_fg']}; font-weight: 600; }}
#BulkBar {{ background: {c['sel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
#Log {{ background: {c['log_bg']}; color: {c['log_fg']}; border: none; border-radius: 8px; padding: 8px; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9pt; }}
"""
