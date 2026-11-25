"""Profiles, laid out like the website: a grid of Profile cards, and a tabbed editor with section cards.

Cards show the photo or initials, the headline, how complete the Profile is,
email, phone and who it is shared with. Admins also create, share and delete
Profiles and change the photo. Bidders and Callers edit the Profiles they work
on (personal, address, links, application defaults, education, work, prompts,
Avoid lists).

The server answers a Profile with its card fields at the top and the form's
fields under `profile`; both are read.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from .. import tasks, theme
from ..state import AppState
from .icons import pixmap
from .widgets import button, icon_button, label, page_header, with_icon

US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
    ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "District of Columbia"), ("FL", "Florida"),
    ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"),
    ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
    ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]
COUNTRIES = ["United States", "Canada", "United Kingdom", "Australia", "Germany", "India", "Philippines", "Mexico",
             "Other"]
TIMEZONES = [("America/New_York", "Eastern Time (ET)"), ("America/Chicago", "Central Time (CT)"),
             ("America/Denver", "Mountain Time (MT)"), ("America/Phoenix", "Arizona (MST)"),
             ("America/Los_Angeles", "Pacific Time (PT)"), ("America/Anchorage", "Alaska Time"),
             ("Pacific/Honolulu", "Hawaii Time"), ("America/Toronto", "Toronto"), ("America/Vancouver", "Vancouver"),
             ("Europe/London", "London"), ("UTC", "UTC")]
DEGREES = ["High School Diploma", "GED", "Associate's Degree", "Bachelor's Degree", "Master's Degree", "MBA",
           "Doctorate (PhD)", "Professional Degree (JD, MD…)"]
OPTIONS = {
    "gender": ["Male", "Female", "Non-binary", "Prefer not to say", "Other"],
    "ethnicity": ["American Indian or Alaska Native", "Asian", "Black or African American", "Hispanic or Latino",
                  "Native Hawaiian or Other Pacific Islander", "White", "Two or more races", "Prefer not to say"],
    "disabilityStatus": ["Yes, I have a disability", "No, I do not have a disability", "Prefer not to say"],
    "veteranStatus": ["I am a veteran", "I am not a veteran", "Prefer not to say"],
    "lgbtqIdentity": ["Yes", "No", "Prefer not to say"],
    "birthYear": [str(y) for y in range(2008, 1939, -1)],
    "securityClearance": ["None", "Confidential", "Secret", "Top Secret", "Top Secret / SCI", "Prefer not to say"],
    "drugTestWillingness": ["Willing", "Not willing", "Prefer not to say"],
    "noticePeriod": ["Immediately", "1 week", "2 weeks", "30 days", "60 days", "90 days", "Other"],
    "openToRelocation": ["Yes", "No", "Negotiable"],
    "inPersonAvailability": ["Yes", "No", "Limited / case by case"],
    "requireAccommodations": ["Yes", "No", "Prefer not to say"],
}
# The form's plain text fields (everything but the lists, the checkbox and the template).
TEXT_KEYS = ["firstName", "middleName", "lastName", "preferredFirstName", "preferredLastName", "dateOfBirth",
             "email", "phone", "location", "addressLine", "city", "state", "zipCode", "county", "country", "timezone",
             "linkedinUrl", "githubUrl", "portfolioUrl", "otherUrl", *OPTIONS.keys()]


def _flat(detail: dict) -> dict:
    """The card fields and the form fields (`profile`) in one dict."""
    detail = dict(detail or {})
    inner = detail.pop("profile", None)
    if isinstance(inner, dict):
        detail.update(inner)
    return detail


def _initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "P"


def _message(error: Exception) -> str:
    return getattr(error, "message", str(error))


class Avatar(QLabel):
    """A round photo, or initials on the accent colour."""

    def __init__(self, name: str, size: int = 40):
        super().__init__()
        self.setFixedSize(size, size)
        self._name = name
        self._photo: QPixmap | None = None
        self.update()

    def set_photo(self, data: bytes | None) -> None:
        pix = QPixmap()
        self._photo = pix if data and pix.loadFromData(data) else None
        self.update()

    def set_name(self, name: str) -> None:
        self._name = name
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addEllipse(QRectF(self.rect()))
        p.setClipPath(path)
        if self._photo:
            scaled = self._photo.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        else:
            p.fillPath(path, QColor(theme.colors()["accent"]))
            p.setPen(QColor(theme.colors()["accent_fg"]))
            font = QFont(self.font())
            font.setPixelSize(max(9, int(self.height() * 0.36)))
            font.setBold(True)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, _initials(self._name))
        p.end()


def _load_photo(state: AppState, url: str | None, avatar: Avatar, owner: QWidget) -> None:
    if not url:
        return
    full = url if url.startswith("http") else state.session.server.rstrip("/") + url
    tasks.run(lambda: state.api.file_bytes(full), avatar.set_photo, lambda _e: None, owner=owner)


# ============================================================================ cards
class ProfileCard(QFrame):
    open = Signal(str)
    share = Signal(str)
    delete = Signal(str)

    def __init__(self, state: AppState, summary: dict, admin: bool):
        super().__init__()
        self.setObjectName("ProfileCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(300)
        self.setFixedHeight(270)
        pid = summary.get("id", "")
        self.pid = pid
        c = theme.colors()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        name = summary.get("displayName") or "Profile"
        avatar = Avatar(name, 40)
        _load_photo(state, summary.get("photoUrl"), avatar, self)
        top.addWidget(avatar)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(name, "CardName"))
        names.addWidget(label(summary.get("headline") or "No title yet", "Muted"))
        top.addLayout(names, 1)
        more = icon_button("more", "More")
        more.setObjectName("Ghost")
        more.setFixedSize(30, 30)
        menu = QMenu(self)
        menu.addAction("Edit", lambda: self.open.emit(pid))
        if admin:
            menu.addAction("Share with users…", lambda: self.share.emit(pid))
            menu.addSeparator()
            menu.addAction("Delete…", lambda: self.delete.emit(pid))
        more.setMenu(menu)
        top.addWidget(more, 0, Qt.AlignTop)
        lay.addLayout(top)
        lay.addSpacing(4)

        done = int(summary.get("completionPercent") or 0)
        row = QHBoxLayout()
        row.addWidget(label("PROFILE COMPLETION", "Label"))
        row.addStretch(1)
        row.addWidget(label(f"{done}%", "Strong"))
        lay.addLayout(row)
        bar = QProgressBar()
        bar.setObjectName("Completion")
        bar.setRange(0, 100)
        bar.setValue(done)
        bar.setTextVisible(False)
        bar.setFixedHeight(7)
        lay.addWidget(bar)
        lay.addSpacing(4)

        for icon_name, text in (("mail", summary.get("email")), ("phone", summary.get("phone"))):
            line = QHBoxLayout()
            line.setSpacing(8)
            ic = QLabel()
            ic.setPixmap(pixmap(icon_name, c["muted"], 15, 1.8))
            line.addWidget(ic)
            line.addWidget(label(text or "—", "" if text else "Muted"), 1)
            lay.addLayout(line)
        lay.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(pixmap("share", c["muted"], 15, 1.8))
        bottom.addWidget(ic)
        shared = summary.get("sharedWith") or []
        if shared:
            for user in shared[:6]:
                dot = Avatar(user.get("displayName") or user.get("email", ""), 28)
                dot.setToolTip(f"{user.get('displayName', '')}  ·  {user.get('email', '')}")
                bottom.addWidget(dot)
            if len(shared) > 6:
                bottom.addWidget(label(f"+{len(shared) - 6}", "Muted"))
        else:
            bottom.addWidget(label("Not shared" if admin else "", "Faint"))
        bottom.addStretch(1)
        if admin:
            plus = icon_button("plus", "Share with users", lambda: self.share.emit(pid))
            plus.setObjectName("RoundButton")
            bottom.addWidget(plus)
        lay.addLayout(bottom)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.open.emit(self.pid)
        super().mouseReleaseEvent(event)


class NewProfileCard(QFrame):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("NewCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(300)
        self.setFixedHeight(270)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(8)
        lay.addStretch(1)
        plus = QLabel()
        plus.setObjectName("PlusBubble")
        plus.setFixedSize(48, 48)
        plus.setAlignment(Qt.AlignCenter)
        plus.setPixmap(pixmap("plus", theme.colors()["accent"], 22, 2.0))
        lay.addWidget(plus, 0, Qt.AlignHCenter)
        title = label("Create new profile", "CardName")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        note = label("Start another profile for a different role, resume version, or search strategy.", "Muted",
                     wrap=True)
        note.setAlignment(Qt.AlignCenter)
        lay.addWidget(note)
        lay.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ============================================================================ editor building blocks
def _section(title: str, subtitle: str, icon_name: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Section")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(24, 20, 24, 22)
    lay.setSpacing(14)
    head = QHBoxLayout()
    head.setSpacing(12)
    if icon_name:
        bubble = QLabel()
        bubble.setObjectName("IconBubble")
        bubble.setFixedSize(34, 34)
        bubble.setAlignment(Qt.AlignCenter)
        bubble.setPixmap(pixmap(icon_name, theme.colors()["accent"], 17, 1.9))
        head.addWidget(bubble, 0, Qt.AlignTop)
    names = QVBoxLayout()
    names.setSpacing(2)
    names.addWidget(label(title, "SectionTitle"))
    if subtitle:
        names.addWidget(label(subtitle, "Muted", wrap=True))
    head.addLayout(names, 1)
    lay.addLayout(head)
    return card, lay


def _field(title: str, widget: QWidget, required: bool = False, note: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    text = f"{title} <span style='color:#EF4444'>*</span>" if required else title
    lab = QLabel(text)
    lab.setObjectName("FieldLabel")
    lay.addWidget(lab)
    lay.addWidget(widget)
    if note:
        lay.addWidget(label(note, "Faint", wrap=True))
    return box


def _grid(widgets: list[QWidget], columns: int) -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(14)
    for i, w in enumerate(widgets):
        grid.addWidget(w, i // columns, i % columns, Qt.AlignTop)
    for col in range(columns):
        grid.setColumnStretch(col, 1)
    return grid


def _combo(options, editable: bool = True, placeholder: str = "Select…") -> QComboBox:
    combo = QComboBox()
    combo.setEditable(editable)
    combo.addItem("", "")
    for opt in options:
        value, text = opt if isinstance(opt, tuple) else (opt, opt)
        combo.addItem(text, value)
    if editable:
        combo.lineEdit().setPlaceholderText(placeholder)
    combo.setMinimumWidth(120)
    return combo


def _set_combo(combo: QComboBox, value: str) -> None:
    value = value or ""
    index = combo.findData(value)
    if index < 0:
        index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif combo.isEditable():
        combo.setEditText(value)
    else:
        combo.addItem(value, value)
        combo.setCurrentIndex(combo.count() - 1)


def _combo_value(combo: QComboBox) -> str:
    text = combo.currentText().strip()
    if combo.currentIndex() >= 0 and combo.itemText(combo.currentIndex()) == text:
        return str(combo.currentData() or "")
    return text


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(inner)
    return area


def _tab_page() -> tuple[QScrollArea, QVBoxLayout]:
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(0, 16, 12, 16)
    lay.setSpacing(16)
    return _scroll(inner), lay


class EntryList(QWidget):
    """Education or Work Experience: one card per entry, with move up/down and remove."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind  # "education" | "work"
        self.entries: list[dict] = []
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(12)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(12)
        self.lay.addLayout(self.rows)
        self.empty = label("", "Muted")
        self.lay.addWidget(self.empty)
        add = button("+ Add education" if kind == "education" else "+ Add work experience", "", lambda: self.add({}))
        self.lay.addWidget(add, 0, Qt.AlignLeft)

    def set_entries(self, rows: list[dict]) -> None:
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.entries = []
        for row in rows or []:
            self.add(row)
        self._refresh()

    def add(self, row: dict) -> None:
        box = QFrame()
        box.setObjectName("Entry")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        title = label("", "Strong")
        head.addWidget(title, 1)
        entry: dict = {"id": row.get("id"), "box": box, "title": title, "fields": {}}
        for icon_name, tip, step in (("chevron-up", "Move up", -1), ("chevron", "Move down", 1)):
            head.addWidget(icon_button(icon_name, tip, lambda _=False, e=entry, s=step: self._move(e, s)))
        head.addWidget(icon_button("x", "Remove", lambda _=False, e=entry: self._remove(e)))
        lay.addLayout(head)
        if self.kind == "education":
            specs = [("degree", "Degree", _combo(DEGREES), True), ("major", "Major / Field of study", QLineEdit(), True),
                     ("university", "School / University", QLineEdit(), True), ("location", "Location", QLineEdit(), False),
                     ("startDate", "Start (YYYY-MM-DD)", QLineEdit(), False), ("endDate", "End (YYYY-MM-DD)", QLineEdit(), False)]
            now_text = "I'm currently enrolled here"
        else:
            specs = [("company", "Company", QLineEdit(), True), ("title", "Job title", QLineEdit(), True),
                     ("location", "Location", QLineEdit(), False), ("startDate", "Start (YYYY-MM)", QLineEdit(), True),
                     ("endDate", "End (YYYY-MM)", QLineEdit(), False)]
            now_text = "I currently work here"
        widgets = []
        for key, text, widget, required in specs:
            value = str(row.get(key) or "")
            if isinstance(widget, QComboBox):
                _set_combo(widget, value)
                widget.currentTextChanged.connect(lambda _t, e=entry: self._title(e))
            else:
                widget.setText(value)
                widget.textChanged.connect(lambda _t, e=entry: self._title(e))
            entry["fields"][key] = widget
            widgets.append(_field(text, widget, required))
        lay.addLayout(_grid(widgets, 3 if self.kind == "education" else 3))
        current = QCheckBox(now_text)
        current.setChecked(bool(row) and not row.get("endDate"))
        end = entry["fields"]["endDate"]
        end.setEnabled(not current.isChecked())
        current.toggled.connect(lambda on, e=end: (e.setEnabled(not on), e.clear() if on else None))
        entry["current"] = current
        lay.addWidget(current)
        self.entries.append(entry)
        self.rows.addWidget(box)
        self._title(entry)
        self._refresh()

    def _title(self, entry: dict) -> None:
        f = entry["fields"]
        index = self.entries.index(entry) + 1 if entry in self.entries else len(self.entries) + 1
        if self.kind == "education":
            text = f["university"].text().strip() or f"Education {index}"
        else:
            text = f["company"].text().strip() or f"Role {index}"
        entry["title"].setText(text)

    def _move(self, entry: dict, step: int) -> None:
        i = self.entries.index(entry)
        j = i + step
        if not 0 <= j < len(self.entries):
            return
        self.entries[i], self.entries[j] = self.entries[j], self.entries[i]
        self.rows.removeWidget(entry["box"])
        self.rows.insertWidget(j, entry["box"])

    def _remove(self, entry: dict) -> None:
        self.entries.remove(entry)
        self.rows.removeWidget(entry["box"])
        entry["box"].deleteLater()
        self._refresh()

    def _refresh(self) -> None:
        self.empty.setText("Nothing here yet." if not self.entries else "")
        self.empty.setVisible(not self.entries)

    def values(self) -> list[dict]:
        out = []
        for entry in self.entries:
            row = {}
            for key, widget in entry["fields"].items():
                row[key] = _combo_value(widget) if isinstance(widget, QComboBox) else widget.text().strip()
            if not any(row.values()):
                continue
            if entry["current"].isChecked() or not row.get("endDate"):
                row["endDate"] = None
            if entry.get("id"):
                row["id"] = entry["id"]
            out.append(row)
        return out


# ============================================================================ editor
class ProfileEditor(QWidget):
    back = Signal()
    saved = Signal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.pid: str | None = None
        self.detail: dict = {}
        self.inputs: dict[str, QWidget] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.header = page_header("Edit Profile", "Application identity — personal details, education, and work history.")
        self.title = self.header.findChild(QLabel, "Title")
        self.subtitle = self.header.findChild(QLabel, "Subtitle")
        head.addWidget(self.header, 1)
        self.status = label("", "Ok")
        head.addWidget(self.status, 0, Qt.AlignVCenter)
        self.back_btn = with_icon(button("Profiles", "", self.back.emit), "chevron-left")
        head.addWidget(self.back_btn, 0, Qt.AlignTop)
        self.save_btn = button("Save", "Primary", self._save)
        head.addWidget(self.save_btn, 0, Qt.AlignTop)
        lay.addLayout(head)
        self.error = label("", "Error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("LineTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._personal(), "Personal")
        self.tabs.addTab(self._links(), "Links")
        self.tabs.addTab(self._defaults(), "Application Defaults")
        page, body = _tab_page()
        card, cl = _section("Education", "Schools and degrees, newest first.", "school")
        self.education = EntryList("education")
        cl.addWidget(self.education)
        body.addWidget(card)
        body.addStretch(1)
        self.tabs.addTab(page, "Education")
        page, body = _tab_page()
        card, cl = _section("Work Experience", "Jobs, newest first. The resume is written from these.", "briefcase")
        self.work = EntryList("work")
        cl.addWidget(self.work)
        body.addWidget(card)
        body.addStretch(1)
        self.tabs.addTab(page, "Work Experience")
        self.tabs.addTab(self._prompts(), "Prompts & Template")
        self.tabs.addTab(self._avoid(), "Avoid")
        lay.addWidget(self.tabs, 1)

    # -------------------------------------------------------------- tabs
    def _text(self, key: str, placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        self.inputs[key] = edit
        return edit

    def _choice(self, key: str, options, editable: bool = True) -> QComboBox:
        combo = _combo(options, editable)
        self.inputs[key] = combo
        return combo

    def _personal(self) -> QWidget:
        page, body = _tab_page()
        card, lay = _section("Profile Details", "Name, email, and phone for this application identity.", "user")
        photo_row = QHBoxLayout()
        photo_row.setSpacing(14)
        self.avatar = Avatar("", 72)
        photo_row.addWidget(self.avatar)
        photo_col = QVBoxLayout()
        photo_col.setSpacing(6)
        photo_col.addWidget(label("Photo", "FieldLabel"))
        buttons = QHBoxLayout()
        self.upload_btn = button("Upload photo", "", self._upload_photo, "JPG, PNG, WebP or GIF, up to 5 MB")
        self.remove_photo_btn = button("Remove", "", self._remove_photo)
        buttons.addWidget(self.upload_btn)
        buttons.addWidget(self.remove_photo_btn)
        buttons.addStretch(1)
        photo_col.addLayout(buttons)
        self.photo_note = label("Saved on the romva server.", "Faint")
        photo_col.addWidget(self.photo_note)
        photo_row.addLayout(photo_col, 1)
        lay.addLayout(photo_row)
        lay.addLayout(_grid([_field("First Name", self._text("firstName", "First name"), True),
                             _field("Middle Name", self._text("middleName", "Middle name")),
                             _field("Last Name", self._text("lastName", "Last name"), True)], 3))
        self.has_preferred = QCheckBox("I have a preferred name")
        lay.addWidget(self.has_preferred)
        self.preferred = QWidget()
        pl = QVBoxLayout(self.preferred)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addLayout(_grid([_field("Preferred First Name", self._text("preferredFirstName", "Preferred first name")),
                            _field("Preferred Last Name", self._text("preferredLastName", "Preferred last name"))], 2))
        lay.addWidget(self.preferred)
        self.has_preferred.toggled.connect(self.preferred.setVisible)
        self.preferred.hide()
        lay.addLayout(_grid([
            _field("Email", self._text("email", "name@example.com"), True,
                   "Candidate contact email for applications — not a User login."),
            _field("Phone Number", self._text("phone", "(555) 123-4567"), True),
        ], 2))
        lay.addLayout(_grid([_field("Date of Birth", self._text("dateOfBirth", "YYYY-MM-DD"))], 2))
        body.addWidget(card)

        card, lay = _section("Address Information", "Location, postal details, and timezone used on applications.",
                             "map")
        lay.addWidget(_field("Address Line", self._text("addressLine", "Street address"), True))
        lay.addLayout(_grid([
            _field("City", self._text("city", "City"), True),
            _field("State", self._choice("state", US_STATES), True),
            _field("ZIP Code", self._text("zipCode", "ZIP code"), True),
            _field("County", self._text("county", "County")),
            _field("Country", self._choice("country", COUNTRIES), True),
            _field("Timezone", self._choice("timezone", TIMEZONES)),
        ], 3))
        lay.addWidget(_field("Location shown on the resume", self._text("location", "e.g. Austin, TX"), False,
                             "Empty = made from the city and state."))
        body.addWidget(card)
        body.addStretch(1)
        return page

    def _links(self) -> QWidget:
        page, body = _tab_page()
        card, lay = _section("Links", "Profiles and sites that application forms ask for.", "link")
        lay.addLayout(_grid([
            _field("LinkedIn", self._text("linkedinUrl", "https://linkedin.com/in/…")),
            _field("GitHub", self._text("githubUrl", "https://github.com/…")),
            _field("Portfolio", self._text("portfolioUrl", "https://…")),
            _field("Other", self._text("otherUrl", "https://…")),
        ], 2))
        body.addWidget(card)
        body.addStretch(1)
        return page

    def _defaults(self) -> QWidget:
        page, body = _tab_page()
        card, lay = _section("Application Defaults", "Answers the form filler uses on job applications.", "check")
        lay.addWidget(label("Authorized to work in", "FieldLabel"))
        self.countries: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        for i, country in enumerate(COUNTRIES):
            box = QCheckBox(country)
            self.countries[country] = box
            grid.addWidget(box, i // 4, i % 4)
        lay.addLayout(grid)
        body.addWidget(card)
        groups = [
            ("Demographics", "Voluntary self-identification (EEO) answers.",
             [("gender", "Gender"), ("ethnicity", "Ethnicity"), ("disabilityStatus", "Disability Status"),
              ("veteranStatus", "Veteran Status"), ("lgbtqIdentity", "Do you identify as LGBTQ+?"),
              ("birthYear", "Birth Year")]),
            ("Screening & Compliance", "", [("securityClearance", "Security Clearance"),
                                            ("drugTestWillingness", "Drug Test")]),
            ("Location & Availability", "", [("noticePeriod", "Notice Period"),
                                             ("openToRelocation", "Open to relocation"),
                                             ("inPersonAvailability", "In-person interviews / meetings"),
                                             ("requireAccommodations", "Require Accommodations")]),
        ]
        for title, subtitle, fields in groups:
            card, lay = _section(title, subtitle)
            lay.addLayout(_grid([_field(text, self._choice(key, OPTIONS[key])) for key, text in fields], 3))
            body.addWidget(card)
        body.addStretch(1)
        return page

    def _prompts(self) -> QWidget:
        page, body = _tab_page()
        card, lay = _section("Template", "The Word template the resume is made from.", "file")
        self.template = QComboBox()
        lay.addWidget(_field("Resume template", self.template))
        body.addWidget(card)
        card, lay = _section("Prompts", "What the AI is asked. Empty = the default from AI settings.", "sparkles")
        self.resume_prompt = QPlainTextEdit()
        self.resume_prompt.setMinimumHeight(220)
        lay.addWidget(_field("Resume prompt", self.resume_prompt))
        self.cover_prompt = QPlainTextEdit()
        self.cover_prompt.setMinimumHeight(160)
        lay.addWidget(_field("Cover letter prompt", self.cover_prompt, note="Empty = no cover letter."))
        body.addWidget(card)
        body.addStretch(1)
        return page

    def _avoid(self) -> QWidget:
        page, body = _tab_page()
        card, lay = _section("Avoid", "The scraper doesn't save jobs that match these. One per line.", "x")
        self.avoid_roles = QPlainTextEdit()
        self.avoid_companies = QPlainTextEdit()
        lay.addLayout(_grid([_field("Roles to skip", self.avoid_roles),
                             _field("Companies to skip", self.avoid_companies)], 2))
        self.avoid_roles.setMinimumHeight(260)
        self.avoid_companies.setMinimumHeight(260)
        body.addWidget(card)
        body.addStretch(1)
        return page

    # -------------------------------------------------------------- data
    @property
    def admin(self) -> bool:
        return self.state.session.is_admin

    def _set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def open_profile(self, pid: str | None) -> None:
        """Load a Profile (or a blank form for a new one, `pid=None`)."""
        self.pid = pid
        self.tabs.setCurrentIndex(0)
        self._set_error("")
        self.status.setText("")
        self.title.setText("Edit Profile" if pid else "New Profile")
        if self.subtitle:
            self.subtitle.setText("Application identity — personal details, education, and work history."
                                  + (" Share it with users from the Profiles list." if self.admin else ""))
        for w in (self.upload_btn, self.remove_photo_btn):
            w.setVisible(self.admin and bool(pid))
        self.photo_note.setText("Saved on the romva server." if self.admin and pid
                                else ("Save the Profile first, then add a photo." if self.admin
                                      else "Your admin sets the photo."))
        self._fill({}, {}, {})
        self.save_btn.setEnabled(not pid)
        api, admin = self.state.api, self.admin
        if not pid:
            if admin:  # the template list for a new Profile
                tasks.run(lambda: api.request("GET", "/api/resume/maker/templates"), self._templates_only,
                          lambda _e: None, owner=self)
            return
        self.status.setText("Loading…")

        def fetch():
            detail = api.request("GET", f"/api/admin/profiles/{pid}") if admin else api.profile_detail(pid)
            return detail, api.prompts(pid), api.avoid(pid)

        def done(result, p=pid):
            if p == self.pid:
                self.status.setText("")
                self._fill(*result)
                self.save_btn.setEnabled(True)

        def failed(error, p=pid):
            if p == self.pid:
                self.status.setText("")
                self._set_error(_message(error))

        tasks.run(fetch, done, failed, owner=self)

    def _templates_only(self, data) -> None:
        items = data.get("templates", data) if isinstance(data, dict) else data
        self.template.clear()
        for t in items or []:
            if isinstance(t, dict):
                self.template.addItem(t.get("name", t.get("id")), t.get("id"))

    def _fill(self, detail: dict, prompts: dict, avoid: dict) -> None:
        self.detail = _flat(detail)
        d = self.detail
        for key, widget in self.inputs.items():
            value = d.get(key, "")
            value = "" if value is None else str(value)
            if isinstance(widget, QComboBox):
                _set_combo(widget, value)
            else:
                widget.setText(value)
        self.has_preferred.setChecked(bool(d.get("hasPreferredName")))
        self.preferred.setVisible(self.has_preferred.isChecked())
        chosen = set(d.get("authorizedCountries") or [])
        for country, box in self.countries.items():
            box.setChecked(country in chosen)
        self.education.set_entries(d.get("education") or [])
        self.work.set_entries(d.get("workExperience") or [])
        name = " ".join(x for x in (d.get("firstName"), d.get("lastName")) if x) or d.get("displayName") or ""
        self.avatar.set_name(name or "Profile")
        self.avatar.set_photo(None)
        _load_photo(self.state, d.get("photoUrl"), self.avatar, self)
        self.remove_photo_btn.setEnabled(bool(d.get("photoUrl")))
        if self.pid and name:
            self.title.setText(f"Edit Profile · {name}")
        prompts = prompts or {}
        self.template.clear()
        for t in prompts.get("templates", []):
            self.template.addItem(t.get("name", t.get("id")), t.get("id"))
        index = self.template.findData(prompts.get("resumeTemplateId") or d.get("resumeTemplateId"))
        if index >= 0:
            self.template.setCurrentIndex(index)
        self.resume_prompt.setPlainText(prompts.get("resumePrompt") or "")
        self.cover_prompt.setPlainText(prompts.get("coverLetterPrompt") or "")
        self.avoid_roles.setPlainText("\n".join((avoid or {}).get("avoidRoles", [])))
        self.avoid_companies.setPlainText("\n".join((avoid or {}).get("avoidCompanies", [])))

    def _body(self) -> dict:
        body: dict = {}
        for key, widget in self.inputs.items():
            body[key] = _combo_value(widget) if isinstance(widget, QComboBox) else widget.text().strip()
        body["hasPreferredName"] = self.has_preferred.isChecked()
        body["authorizedCountries"] = [c for c, box in self.countries.items() if box.isChecked()]
        # Keep any country saved before that isn't on the list.
        body["authorizedCountries"] += [c for c in (self.detail.get("authorizedCountries") or [])
                                        if c not in self.countries]
        body["education"] = self.education.values()
        body["workExperience"] = self.work.values()
        template = self.template.currentData() or self.detail.get("resumeTemplateId")
        if template:
            body["resumeTemplateId"] = template
        return body

    def _save(self) -> None:
        required = [("firstName", "First name"), ("lastName", "Last name"), ("email", "Email"), ("phone", "Phone")]
        body = self._body()
        missing = [text for key, text in required if not body.get(key)]
        if missing:
            self.tabs.setCurrentIndex(0)
            self._set_error("Fill in: " + ", ".join(missing) + ".")
            return
        api, pid, admin = self.state.api, self.pid, self.admin
        prompts = {"resumePrompt": self.resume_prompt.toPlainText().strip() or None,
                   "coverLetterPrompt": self.cover_prompt.toPlainText().strip() or None}
        if self.template.currentData():
            prompts["resumeTemplateId"] = self.template.currentData()
        avoid = {"avoidRoles": [x.strip() for x in self.avoid_roles.toPlainText().splitlines() if x.strip()],
                 "avoidCompanies": [x.strip() for x in self.avoid_companies.toPlainText().splitlines() if x.strip()]}

        def run():
            if pid is None:
                detail = api.request("POST", "/api/admin/profiles", json_body=body)
                new_id = detail.get("id")
            elif admin:
                detail = api.request("PUT", f"/api/admin/profiles/{pid}", json_body=body)
                new_id = pid
            else:
                detail = api.save_profile(pid, body)
                new_id = pid
            api.save_prompts(new_id, prompts)
            api.save_avoid(new_id, avoid)
            return new_id, detail

        self.save_btn.setEnabled(False)
        self.status.setText("Saving…")
        self._set_error("")

        def done(result):
            new_id, detail = result
            self.save_btn.setEnabled(True)
            self.status.setText("✓ Saved")
            created = self.pid is None
            self.pid = new_id
            self.detail = _flat(detail) or self.detail
            self.saved.emit(new_id)
            if created:
                self.open_profile(new_id)
                self.status.setText("✓ Created")

        def failed(error):
            self.save_btn.setEnabled(True)
            self.status.setText("")
            message = _message(error)
            if getattr(error, "status", 0) == 404 and not admin:
                message += "\nYour server may not have the Profile editing update yet."
            self._set_error(message)

        tasks.run(run, done, failed, owner=self)

    def _upload_photo(self) -> None:
        if not self.pid:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a photo", "", "Images (*.jpg *.jpeg *.png *.webp *.gif)")
        if not path:
            return
        kind = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                "gif": "image/gif"}.get(path.rsplit(".", 1)[-1].lower(), "image/jpeg")
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as error:
            QMessageBox.warning(self, "Photo", str(error))
            return
        if len(data) > 5 * 1024 * 1024:
            QMessageBox.warning(self, "Photo", "The photo is over 5 MB. Choose a smaller one.")
            return
        pid, api = self.pid, self.state.api
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        self.status.setText("Uploading photo…")

        def done(result):
            self.status.setText("✓ Photo saved")
            self.avatar.set_photo(data)
            self.remove_photo_btn.setEnabled(True)
            self.detail["photoUrl"] = _flat(result or {}).get("photoUrl") or "set"
            self.saved.emit(pid)

        def failed(error):
            self.status.setText("")
            QMessageBox.warning(self, "Photo", _message(error))

        tasks.run(lambda: api.request("POST", f"/api/admin/profiles/{pid}/photo",
                                      files={"photo": (name, data, kind)}), done, failed, owner=self)

    def _remove_photo(self) -> None:
        if not self.pid:
            return
        pid, api = self.pid, self.state.api

        def done(_r):
            self.avatar.set_photo(None)
            self.remove_photo_btn.setEnabled(False)
            self.status.setText("Photo removed")
            self.saved.emit(pid)

        tasks.run(lambda: api.request("DELETE", f"/api/admin/profiles/{pid}/photo"), done,
                  lambda e: QMessageBox.warning(self, "Photo", _message(e)), owner=self)


# ============================================================================ page
class ProfilesPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.summaries: list[dict] = []
        self._columns = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # The grid of cards.
        grid_page = QWidget()
        lay = QVBoxLayout(grid_page)
        lay.setContentsMargins(28, 22, 28, 16)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(8)
        admin = state.session.is_admin
        head.addWidget(page_header("Profiles", "Choose a profile to continue editing" + (
            ", or add another one for a different role, resume version, or search strategy." if admin else ".")), 1)
        self.refresh_btn = with_icon(button("Refresh", "", self.reload), "refresh")
        head.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        if admin:
            head.addWidget(with_icon(button("New profile", "Primary", lambda: self._open(None)), "plus", "accent_fg"),
                           0, Qt.AlignTop)
        lay.addLayout(head)
        self.count = label("", "Muted")
        lay.addWidget(self.count)
        self.error = label("", "Error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        self.cards_box = QWidget()
        self.cards = QGridLayout(self.cards_box)
        self.cards.setContentsMargins(0, 4, 8, 8)
        self.cards.setHorizontalSpacing(16)
        self.cards.setVerticalSpacing(16)
        lay.addWidget(_scroll(self.cards_box), 1)
        self.stack.addWidget(grid_page)

        # The editor.
        edit_page = QWidget()
        el = QVBoxLayout(edit_page)
        el.setContentsMargins(28, 22, 28, 16)
        self.editor = ProfileEditor(state)
        self.editor.back.connect(self._back)
        self.editor.saved.connect(lambda _pid: (self.reload(), self.state.load_profiles()))
        el.addWidget(self.editor)
        self.stack.addWidget(edit_page)

        state.profiles_changed.connect(lambda: self.reload() if self.stack.currentIndex() == 0 else None)
        self._loaded = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        columns = max(1, min(4, (self.width() - 60) // 340))
        if columns != self._columns:
            self._columns = columns
            self._layout_cards()

    # -------------------------------------------------------------- data
    def reload(self) -> None:
        api, session = self.state.api, self.state.session

        def fetch():
            if session.mode == "token":
                rows = []
                for p in session.token_profiles.values():
                    if p.revoked:
                        continue
                    try:
                        rows.extend(api.request("GET", "/api/profiles", profile_id=p.profile_id) or [])
                    except Exception:  # noqa: BLE001 - one revoked token must not hide the others
                        pass
                return rows
            if session.is_admin:
                return api.request("GET", "/api/admin/profiles")
            return api.request("GET", "/api/profiles")

        def failed(error):
            self.error.setText(_message(error))
            self.error.show()

        tasks.run(fetch, self._show, failed, owner=self)

    def _show(self, rows: list[dict]) -> None:
        self.error.hide()
        self.summaries = [_flat(r) | {"id": r.get("id")} for r in (rows or [])]
        for s, r in zip(self.summaries, rows or []):
            # The card fields win over the form's (displayName, photoUrl…).
            s.update({k: v for k, v in r.items() if k != "profile"})
        n = len(self.summaries)
        self.count.setText(f"{n} profile{'s' if n != 1 else ''}")
        self._layout_cards()

    def _layout_cards(self) -> None:
        while self.cards.count():
            w = self.cards.takeAt(0).widget()
            if w:
                w.deleteLater()
        columns = self._columns or 3
        admin = self.state.session.is_admin
        widgets: list[QWidget] = []
        if admin:
            new = NewProfileCard()
            new.clicked.connect(lambda: self._open(None))
            widgets.append(new)
        for s in self.summaries:
            card = ProfileCard(self.state, s, admin)
            card.open.connect(self._open)
            card.share.connect(self._share)
            card.delete.connect(self._delete)
            widgets.append(card)
        for i, w in enumerate(widgets):
            self.cards.addWidget(w, i // columns, i % columns)
        for col in range(4):
            self.cards.setColumnStretch(col, 1 if col < columns else 0)
        self.cards.setRowStretch(len(widgets) // columns + 1, 1)

    def _open(self, pid: str | None) -> None:
        self.editor.open_profile(pid)
        self.stack.setCurrentIndex(1)

    def _back(self) -> None:
        self.stack.setCurrentIndex(0)
        self.reload()

    def _summary(self, pid: str) -> dict:
        return next((s for s in self.summaries if s.get("id") == pid), {})

    def _share(self, pid: str) -> None:
        tasks.run(lambda: self.state.api.request("GET", "/api/admin/users"),
                  lambda users: self._share_dialog(pid, users),
                  lambda e: QMessageBox.warning(self, "Share", _message(e)), owner=self)

    def _share_dialog(self, pid: str, users: list[dict]) -> None:
        summary = self._summary(pid)
        shared = {u.get("id") for u in summary.get("sharedWith") or []}
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Share {summary.get('displayName', 'Profile')}")
        dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.addWidget(label("Tick the Bidders and Callers who work on this Profile. Admins see every Profile already.",
                            "Muted", wrap=True))
        box = QListWidget()
        from .admin import role_of

        for u in users or []:
            if u.get("role") == "admin":
                continue
            item = QListWidgetItem(f"{u.get('displayName') or u.get('email')}   ·   {role_of(u)}"
                                   + ("   (suspended)" if u.get("status") == "suspended" else ""))
            item.setData(Qt.UserRole, u.get("id"))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if u.get("id") in shared else Qt.Unchecked)
            box.addItem(item)
        lay.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Save")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.rejected.connect(dlg.reject)

        def accept():
            ids = [box.item(i).data(Qt.UserRole) for i in range(box.count()) if box.item(i).checkState() == Qt.Checked]
            dlg.accept()
            tasks.run(lambda: self.state.api.request("PUT", f"/api/admin/profiles/{pid}/shares",
                                                     json_body={"userIds": ids}),
                      lambda _r: self.reload(), lambda e: QMessageBox.warning(self, "Share", _message(e)), owner=self)

        buttons.accepted.connect(accept)
        lay.addWidget(buttons)
        dlg.resize(460, 460)
        dlg.exec()

    def _delete(self, pid: str) -> None:
        name = self._summary(pid).get("displayName", "this Profile")
        if QMessageBox.question(self, "Delete profile",
                                f"Delete {name}? Its tokens and sharing go with it; its applications stay "
                                "but no longer belong to a Profile. This can't be undone.") != QMessageBox.Yes:
            return

        def done(_r):
            self.reload()
            self.state.load_profiles()

        tasks.run(lambda: self.state.api.request("DELETE", f"/api/admin/profiles/{pid}"), done,
                  lambda e: QMessageBox.warning(self, "Delete profile", _message(e)), owner=self)
