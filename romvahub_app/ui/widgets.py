"""Small building blocks shared by the screens."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import theme


def app_icon(size: int = 64) -> QIcon:
    """The app's mark: a blue rounded square with an "r"."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    p.fillPath(path, QColor("#2563EB"))
    p.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", int(size * 0.42))
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, -size * 0.04, size, size), Qt.AlignCenter, "r")
    p.end()
    return QIcon(pix)


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def button(text: str, name: str = "", on_click=None, tip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if name:
        btn.setObjectName(name)
    if on_click:
        btn.clicked.connect(on_click)
    if tip:
        btn.setToolTip(tip)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class Card(QFrame):
    def __init__(self, title: str = "", parent: QWidget | None = None, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(spacing)
        if title:
            self.body.addWidget(label(title.upper(), "Label"))


class Chip(QPushButton):
    """A rounded status label. Clickable when it opens a menu."""

    def __init__(self, text: str, kind: str, clickable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        self.set(text, kind, clickable)

    def set(self, text: str, kind: str, clickable: bool) -> None:
        self.kind = kind
        bg, fg = theme.chip_colors(kind)
        self.setText(f"{text}  ▾" if clickable else text)
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self.setFlat(True)
        self.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 11px; padding: 3px 10px;"
            f" font-size: 8.5pt; font-weight: 600; }} QPushButton:hover {{ background: {bg}; }}"
        )
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class Dot(QLabel):
    def __init__(self, color: str, size: int = 9):
        super().__init__()
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background: {color}; border-radius: {self.width() // 2}px;")


class Segmented(QFrame):
    """A row of mutually exclusive buttons (Light / Dark, 5 / 10 / 100…)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str, name: str = "Seg"):
        super().__init__()
        self.setObjectName("SegBar" if name == "Seg" else "TabBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            btn = button(text, name)
            btn.setCheckable(True)
            btn.setChecked(key == current)
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(btn)
            lay.addWidget(btn)
            self.buttons[key] = btn
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set_current(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class Toast(QFrame):
    """A short message at the bottom of a page, with an optional Undo."""

    undo = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text, 1)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self._undo)
        lay.addWidget(self.undo_btn)
        close = QPushButton("✕")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.hide)
        lay.addWidget(close)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, can_undo: bool = False, seconds: int = 10) -> None:
        self.text.setText(text)
        self.undo_btn.setVisible(can_undo)
        self.show()
        self._timer.start(seconds * 1000)

    def _undo(self) -> None:
        self.hide()
        self.undo.emit()


class Banner(QFrame):
    def __init__(self, text: str = ""):
        super().__init__()
        self.setObjectName("Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.text = QLabel(text)
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.hide()

    def show_text(self, text: str) -> None:
        self.text.setText(text)
        self.setVisible(bool(text))


def page_header(title: str, subtitle: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(label(title, "Title"))
    if subtitle:
        lay.addWidget(label(subtitle, "Subtitle", wrap=True))
    return box


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.colors()['border']};")
    return line


def stat_card(title: str) -> tuple[QFrame, QLabel, QLabel]:
    card = Card()
    card.body.setSpacing(4)
    card.body.addWidget(label(title.upper(), "Label"))
    value = label("–", "Big")
    note = label("", "Muted")
    card.body.addWidget(value)
    card.body.addWidget(note)
    return card, value, note


ICON_SIZE = QSize(16, 16)
