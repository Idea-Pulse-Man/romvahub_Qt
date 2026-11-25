"""Small building blocks shared by the screens."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import theme


LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def logo_pixmap(size: int) -> QPixmap:
    """The romva "R" at `size` px (sharp on high-DPI screens)."""
    pix = QPixmap(str(LOGO))
    if pix.isNull():
        return app_icon_painted(size).pixmap(size, size)
    ratio = 2.0
    pix = pix.scaled(int(size * ratio), int(size * ratio), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pix.setDevicePixelRatio(ratio)
    return pix


def app_icon(size: int = 64) -> QIcon:
    """The app's icon: the romva "R" logo."""
    if LOGO.exists():
        return QIcon(str(LOGO))
    return app_icon_painted(size)


def app_icon_painted(size: int = 64) -> QIcon:
    """Fallback mark (no logo file): a blue rounded square with an "r"."""
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


def brand_mark(size: int = 34) -> QLabel:
    """The logo for the sidebar and the sign-in window."""
    mark = QLabel()
    mark.setFixedSize(size, size)
    mark.setAlignment(Qt.AlignCenter)
    mark.setPixmap(logo_pixmap(size))
    return mark


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
    """A rounded status pill (painted, so it looks the same in every theme). Clickable: a ⌄ after the text."""

    def __init__(self, text: str, kind: str, clickable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFlat(True)
        self.set(text, kind, clickable)

    def set(self, text: str, kind: str, clickable: bool) -> None:
        self.kind, self.label, self.clickable = kind, text, clickable
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        font.setBold(True)
        self._font = font
        width = QFontMetrics(font).horizontalAdvance(text) + 22 + (16 if clickable else 0)
        self.setFixedSize(width, 24)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        bg, fg = theme.chip_colors(self.kind)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        color = QColor(bg)
        if self.underMouse() and self.clickable:
            color = color.darker(108) if theme.colors()["name"] == "light" else color.lighter(125)
        p.fillPath(path, color)
        p.setPen(QColor(fg))
        p.setFont(self._font)
        text_rect = QRectF(11, 0, self.width() - 22 - (16 if self.clickable else 0), self.height())
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.label)
        if self.clickable:
            from .icons import pixmap

            p.drawPixmap(self.width() - 22, 5, pixmap("chevron", fg, 14, 2.4))
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)


def icon_button(name: str, tip: str, on_click=None, color_key: str = "text") -> QPushButton:
    """A 32×32 outlined button with one line icon (Open job, Close…)."""
    from .icons import SMALL, icon

    btn = QPushButton()
    btn.setObjectName("IconButton")
    btn.setIcon(icon(name, theme.colors()[color_key], 16))
    btn.setIconSize(SMALL)
    btn.setToolTip(tip)
    btn.setAccessibleName(tip)
    btn.setCursor(Qt.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def with_icon(btn: QPushButton, name: str, color_key: str = "text", size: int = 14) -> QPushButton:
    from .icons import icon

    btn.setIcon(icon(name, theme.colors()[color_key], size))
    btn.setIconSize(QSize(size, size))
    return btn


class CountTabs(QFrame):
    """The Applications tabs: a pill bar, each tab with its count in a small badge."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str):
        super().__init__()
        self.setObjectName("TabBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        self.counts: dict[str, QLabel] = {}
        self.texts: dict[str, QLabel] = {}
        for key, text in options:
            btn = QPushButton()
            btn.setObjectName("TabButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            inner = QHBoxLayout(btn)
            inner.setContentsMargins(14, 0, 8, 0)
            inner.setSpacing(8)
            name = QLabel(text)
            count = QLabel("·")
            count.setAlignment(Qt.AlignCenter)
            count.setMinimumWidth(24)
            for lab in (name, count):
                lab.setAttribute(Qt.WA_TransparentForMouseEvents)
                inner.addWidget(lab)
            btn.setFixedHeight(34)
            btn.setMinimumWidth(QFontMetrics(btn.font()).horizontalAdvance(text) + 66)
            btn.toggled.connect(lambda _on: self._paint())
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(btn)
            lay.addWidget(btn)
            self.buttons[key], self.counts[key], self.texts[key] = btn, count, name
        self.set_current(current)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set_current(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)
        self._paint()

    def set_counts(self, counts: dict) -> None:
        for key, lab in self.counts.items():
            lab.setText(f"{counts.get(key, 0):,}")
            lab.setMinimumWidth(QFontMetrics(lab.font()).horizontalAdvance(lab.text()) + 14)
        self._paint()

    def _paint(self) -> None:
        c = theme.colors()
        for key, btn in self.buttons.items():
            on = btn.isChecked()
            self.texts[key].setStyleSheet(f"color: {c['text'] if on else c['muted']}; font-weight: 600;")
            bg, fg = (c["accent"], c["accent_fg"]) if on else (c["border"], c["muted"])
            self.counts[key].setStyleSheet(
                f"background: {bg}; color: {fg}; border-radius: 9px; padding: 1px 6px; font-size: 8pt; font-weight: 700;")


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
