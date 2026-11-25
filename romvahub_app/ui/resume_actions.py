"""The Resume check and Remake, shared by the Resume Maker page, the Applications table and the preview window.

The check runs on the server (rules, no AI): placeholders, empty sections,
another person's details, missing employers, the same text twice, missing
files, a cover letter for another company. A flagged application can be
remade: it goes first in the Resume Maker's queue, and its old Resume and
letter stay until the new ones are saved.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QMenu, QMessageBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import tasks, theme
from ..state import AppState
from .widgets import Card, button, icon_button, label, with_icon

# Set by the main window: Remake offers to start it when it is stopped.
MAKER = None


def _message(error: Exception) -> str:
    return getattr(error, "message", str(error))


def bid_profile(state: AppState, bid: dict) -> str | None:
    """The Profile whose token a call needs (token mode); None for an account."""
    if state.session.mode != "token":
        return None
    return (bid.get("candidate") or {}).get("profileId") or state.request_profile


def reasons_of(bid: dict, kind: str | None = None) -> list[str]:
    """The check's reasons for this application — only the Resume's or the letter's with `kind`."""
    check = bid.get("resumeCheck") or {}
    reasons = list(check.get("reasons") or []) if check.get("status") == "flagged" else []
    if kind == "resume":
        return [r for r in reasons if "cover letter" not in r]
    if kind == "cover-letter":
        return [r for r in reasons if "cover letter" in r]
    return reasons


def reasons_tip(reasons: list[str]) -> str:
    return "Needs a remake:\n" + "\n".join(f"•  {r[:1].upper()}{r[1:]}" for r in reasons) if reasons else ""


def _offer_start(parent: QWidget, state: AppState) -> None:
    maker = MAKER
    if maker is None or maker.running:
        return
    answer = QMessageBox.question(parent, "Remake", "The Resume Maker is stopped. Start it now so the remakes are made?")
    if answer == QMessageBox.Yes:
        profile = state.request_profile if state.session.mode == "token" else None
        maker.start(profile)


def remake(parent: QWidget, state: AppState, *, bids: list[dict] | None = None, flagged: bool = False,
           on_done=None) -> None:
    """Queue a remake of these applications (or of every flagged one in reach)."""
    body: dict = {}
    profile = None
    if bids:
        body["ids"] = [b["id"] for b in bids]
        profile = bid_profile(state, bids[0])
    else:
        body["flagged"] = True
        profile = state.request_profile
        if profile and state.session.mode == "account":
            body["profileId"] = profile
    api = state.api

    def done(result):
        n = int((result or {}).get("queued", 0))
        state.data_changed.emit()
        if on_done:
            on_done(n)
        _offer_start(parent, state)

    tasks.run(lambda: api.request("POST", "/api/resume-check/remake", json_body=body,
                                  profile_id=profile if state.session.mode == "token" else None),
              done, lambda e: QMessageBox.warning(parent, "Remake", _message(e)), owner=parent)


def cancel_remake(parent: QWidget, state: AppState, bid: dict, on_done=None) -> None:
    bid_id = bid["id"]
    tasks.run(lambda: state.api.request("DELETE", f"/api/resume-check/remake/{bid_id}",
                                        profile_id=bid_profile(state, bid)),
              lambda _r: (state.data_changed.emit(), on_done() if on_done else None),
              lambda e: QMessageBox.warning(parent, "Remake", _message(e)), owner=parent)


def check_one(parent: QWidget, state: AppState, bid: dict, on_done=None) -> None:
    bid_id = bid["id"]

    def done(result):
        check = (result or {}).get("check")
        state.data_changed.emit()
        if on_done:
            on_done(check)
        if not check:
            QMessageBox.information(parent, "Resume check", "This application has no Resume to check.")
        elif check.get("status") == "ok":
            QMessageBox.information(parent, "Resume check", f"{bid.get('company', '')}: the Resume looks right.")
        else:
            QMessageBox.warning(parent, "Resume check", f"{bid.get('company', '')}\n\n" + reasons_tip(check["reasons"]))

    tasks.run(lambda: state.api.request("POST", f"/api/resume-check/bids/{bid_id}", profile_id=bid_profile(state, bid)),
              done, lambda e: QMessageBox.warning(parent, "Resume check", _message(e)), owner=parent)


def delete_doc(parent: QWidget, state: AppState, bid: dict, kind: str, on_done=None) -> None:
    """Delete the Resume (`resume`) or the cover letter (`cover-letter`), after asking."""
    what = "Resume" if kind == "resume" else "cover letter"
    extra = ("Its files (PDF and Word) are deleted. Click Remake to have a new one made."
             if kind == "resume" else "Click Remake, or the Resume Maker writes it again for a recent Draft.")
    answer = QMessageBox.question(parent, f"Delete {what}",
                                  f"Delete the {what} of {bid.get('company', '')} (#{bid.get('number', '')})?\n\n{extra}")
    if answer != QMessageBox.Yes:
        return
    bid_id = bid["id"]

    def done(_r):
        state.data_changed.emit()
        if on_done:
            on_done()

    tasks.run(lambda: state.api.request("DELETE", f"/api/bids/{bid_id}/{kind}", profile_id=bid_profile(state, bid)),
              done, lambda e: QMessageBox.warning(parent, f"Delete {what}", _message(e)), owner=parent)


def actions_menu(parent: QWidget, state: AppState, bid: dict, on_change=None, open_doc=None) -> QMenu:
    """Check / Remake / Delete for one application."""
    menu = QMenu(parent)
    if open_doc and bid.get("hasResume"):
        menu.addAction("Open Resume", lambda: open_doc(bid, "resume"))
    if bid.get("hasResume"):
        menu.addAction("Check the Resume", lambda: check_one(parent, state, bid, lambda _c: on_change and on_change()))
    if bid.get("remakeRequested"):
        menu.addAction("Cancel the remake", lambda: cancel_remake(parent, state, bid, on_change))
    else:
        menu.addAction("Remake Resume and cover letter",
                       lambda: remake(parent, state, bids=[bid], on_done=lambda _n: on_change and on_change()))
    menu.addSeparator()
    a = menu.addAction("Delete Resume…", lambda: delete_doc(parent, state, bid, "resume", on_change))
    a.setEnabled(bool(bid.get("hasResume")))
    b = menu.addAction("Delete cover letter…", lambda: delete_doc(parent, state, bid, "cover-letter", on_change))
    b.setEnabled(bool(bid.get("hasCoverLetter")))
    return menu


def _ago(value: str | None) -> str:
    if not value:
        return "never"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return moment.strftime("%b %d, %H:%M")


# ============================================================================ the Resume Maker page's card
class ResumeCheckCard(Card):
    """Counts, Check all, Remake flagged, and the list of flagged Drafts with their reasons."""

    open_doc = Signal(dict, str)

    def __init__(self, state: AppState, maker):
        super().__init__("Resume check")
        self.state = state
        self.maker = maker
        self.items: list[dict] = []
        self._loaded = False

        self.body.addWidget(label("Looks over every Draft's saved Resume and cover letter for placeholders "
                                  "(\"[Confirm…]\", \"X%\"), empty sections, another person's details, missing "
                                  "employers, a copy of another Resume, missing files, and a letter for another "
                                  "company. Rules only: no AI, nothing is sent anywhere.", "Muted", wrap=True))
        counts = QHBoxLayout()
        counts.setSpacing(28)
        self.ok = label("–", "Big")
        self.flagged = label("–", "Big")
        self.unchecked = label("–", "Big")
        for value, title in ((self.ok, "Look right"), (self.flagged, "Need a remake"), (self.unchecked, "Not checked yet")):
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(value)
            box.addWidget(label(title, "Muted"))
            counts.addLayout(box)
        counts.addStretch(1)
        self.last = label("", "Faint")
        counts.addWidget(self.last, 0, Qt.AlignBottom)
        self.body.addLayout(counts)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.check_btn = with_icon(button("Check all Resumes", "Primary", self.run_check), "check", "accent_fg")
        self.remake_btn = with_icon(button("Remake flagged", "", self.remake_flagged), "refresh")
        row.addWidget(self.check_btn)
        row.addWidget(self.remake_btn)
        row.addStretch(1)
        row.addWidget(icon_button("refresh", "Refresh the list", self.reload))
        self.body.addLayout(row)
        self.note = label("", "Muted", wrap=True)
        self.note.hide()
        self.body.addWidget(self.note)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Application", "Why it needs a remake", ""])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setWordWrap(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(3, 176)
        self.table.setMinimumHeight(260)
        self.table.setMaximumHeight(420)
        box = QFrame()
        box.setObjectName("TableCard")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(1, 1, 1, 1)
        bl.addWidget(self.table)
        self.table_box = box
        self.body.addWidget(box)
        self.empty = label("", "Muted")
        self.body.addWidget(self.empty)

        state.profile_changed.connect(lambda _p: self.reload() if self._loaded else None)
        state.data_changed.connect(lambda: self.reload() if self._loaded and self.isVisible() else None)
        maker.made.connect(lambda _c: self.reload() if self._loaded else None)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
        self.reload()

    # -------------------------------------------------------------- data
    def _scope(self) -> tuple[dict, str | None]:
        """(query/body with profileId, the token's Profile)."""
        profile = self.state.request_profile
        if self.state.session.mode == "token":
            return {}, profile
        return ({"profileId": profile} if profile else {}), None

    def reload(self) -> None:
        params, token_profile = self._scope()
        api = self.state.api
        tasks.run(lambda: api.request("GET", "/api/resume-check/summary", params=params, profile_id=token_profile),
                  self._show, self._failed, owner=self)

    def _failed(self, error: Exception) -> None:
        status = getattr(error, "status", 0)
        self._note("The server doesn't have the Resume check yet. Run update.bat on the server."
                   if status == 404 else _message(error))

    def _note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def _show(self, data: dict) -> None:
        data = data or {}
        self.ok.setText(str(data.get("ok", 0)))
        self.flagged.setText(str(data.get("flagged", 0)))
        self.unchecked.setText(str(data.get("unchecked", 0)))
        c = theme.colors()
        self.flagged.setStyleSheet(f"color: {c['danger']};" if data.get("flagged") else "")
        self.ok.setStyleSheet(f"color: {c['ok']};" if data.get("ok") else "")
        self.last.setText(f"Last checked {_ago(data.get('lastCheckedAt'))}")
        self.items = list(data.get("items") or [])
        waiting = [i for i in self.items if not i.get("remakeRequested")]
        self.remake_btn.setText(f"Remake {len(waiting)} flagged" if waiting else "Remake flagged")
        self.remake_btn.setEnabled(bool(waiting))
        self.check_btn.setText("Check all Resumes" if data.get("total") else "Check all Resumes")
        self._fill()

    def _fill(self) -> None:
        c = theme.colors()
        show_profile = not self.state.profile_id and self.state.session.mode == "account"
        t = self.table
        t.setRowCount(len(self.items))
        for r, item in enumerate(self.items):
            number = QTableWidgetItem(f"#{item.get('number', '')}")
            number.setForeground(theme_color(c["muted"]))
            t.setItem(r, 0, number)
            who = f"{item.get('company', '')}\n{item.get('role', '')}"
            if show_profile and item.get("profile"):
                who += f"\n{item['profile'].get('name', '')}"
            app = QTableWidgetItem(who)
            app.setToolTip(who)
            t.setItem(r, 1, app)
            reasons = item.get("reasons") or []
            why = QTableWidgetItem("\n".join(f"•  {x[:1].upper()}{x[1:]}" for x in reasons))
            why.setToolTip(reasons_tip(reasons))
            why.setForeground(theme_color(c["text"]))
            t.setItem(r, 2, why)
            t.setCellWidget(r, 3, self._actions(item))
        t.resizeRowsToContents()
        for r in range(t.rowCount()):
            t.setRowHeight(r, max(56, min(t.rowHeight(r) + 10, 140)))
        has = bool(self.items)
        self.table_box.setVisible(has)
        self.empty.setText("" if has else "Nothing needs a remake. Press Check all Resumes to look again.")
        self.empty.setVisible(not has)

    def _bid(self, item: dict) -> dict:
        profile = item.get("profile") or {}
        return {
            "id": item["id"], "number": item.get("number"), "company": item.get("company", ""),
            "role": item.get("role", ""), "hasResume": True, "hasCoverLetter": item.get("hasCoverLetter", False),
            "remakeRequested": item.get("remakeRequested", False),
            "candidate": {"profileId": profile.get("id"), "displayName": profile.get("name", "")},
            "resumeCheck": {"status": "flagged", "reasons": item.get("reasons") or []},
        }

    def _actions(self, item: dict) -> QWidget:
        bid = self._bid(item)
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(4, 0, 6, 0)
        lay.setSpacing(6)
        job = self.maker.job
        if job and str(job.number) == str(item.get("number")):
            lay.addWidget(label("Remaking…", "Accent"))
        elif item.get("remakeRequested"):
            lay.addWidget(label("In queue", "Muted"))
        else:
            btn = button("Remake", "", lambda _=False, b=bid: remake(self, self.state, bids=[b],
                                                                       on_done=lambda _n: self.reload()))
            lay.addWidget(btn)
        more = icon_button("more", "More")
        more.setMenu(actions_menu(self, self.state, bid, self.reload, lambda b, k: self.open_doc.emit(b, k)))
        lay.addWidget(more)
        lay.addStretch(1)
        return box

    # -------------------------------------------------------------- actions
    def run_check(self) -> None:
        body, token_profile = self._scope()
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Checking…")
        self._note("")

        def done(result):
            self.check_btn.setEnabled(True)
            self.check_btn.setText("Check all Resumes")
            result = result or {}
            self._note(f"Checked {result.get('checked', 0)}: {result.get('ok', 0)} look right, "
                       f"{result.get('flagged', 0)} need a remake.")
            self.state.data_changed.emit()
            self.reload()

        def failed(error):
            self.check_btn.setEnabled(True)
            self.check_btn.setText("Check all Resumes")
            self._failed(error)

        tasks.run(lambda: self.state.api.request("POST", "/api/resume-check/run", json_body=body,
                                                 profile_id=token_profile, timeout=600),
                  done, failed, owner=self)

    def remake_flagged(self) -> None:
        waiting = [i for i in self.items if not i.get("remakeRequested")]
        if not waiting:
            return
        if QMessageBox.question(
                self, "Remake flagged",
                f"Remake {len(waiting)} Resume{'s' if len(waiting) != 1 else ''} and their cover letters?\n\n"
                "They go first in the Resume Maker's queue, one by one (about 1–2 minutes each). The old ones stay "
                "until each new one is saved.") != QMessageBox.Yes:
            return
        remake(self, self.state, flagged=True, on_done=lambda n: (self._note(f"{n} queued for a remake."), self.reload()))


def theme_color(value: str):
    from PySide6.QtGui import QBrush, QColor

    return QBrush(QColor(value))
