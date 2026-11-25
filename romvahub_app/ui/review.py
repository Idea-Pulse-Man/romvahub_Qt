"""Review Resumes one by one: the PDF, what the check found, and a decision for each.

    ◀ Previous   Skip ▶   ·   Delete Resume   Remake (R)   Looks fine (A)

"Looks fine" passes this Resume and letter from now on (until they change),
"Remake" puts it first in the Resume Maker's queue (the old one stays until the
new one is saved), "Delete" removes the Resume. Each moves on to the next.
Keys: ← / → to move, A looks fine, R remake.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from .. import tasks, theme
from ..state import AppState
from . import resume_actions
from .widgets import Banner, Chip, Segmented, button, label, with_icon

DECISION = {"ok": ("Looks fine", "offer"), "remake": ("Remake queued", "interview"), "deleted": ("Deleted", "failed"),
            "skip": ("Skipped", "draft")}


def _message(error: Exception) -> str:
    return getattr(error, "message", str(error))


class ReviewDialog(QDialog):
    def __init__(self, state: AppState, bids: list[dict], start: int = 0, parent: QWidget | None = None,
                 title: str = "Review Resumes"):
        super().__init__(parent)
        self.state = state
        self.bids = bids
        self.index = max(0, min(start, len(bids) - 1))
        self.kind = "resume"
        self.decisions: dict[str, str] = {}
        self._cache: dict[tuple[str, str], bytes] = {}
        self._buffer: QBuffer | None = None
        self._busy = False
        self.setWindowTitle(title)
        self.resize(1120, 980)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget()
        head.setObjectName("TopBar")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 12, 18, 12)
        hl.setSpacing(12)
        self.progress = label("", "Accent")
        hl.addWidget(self.progress, 0, Qt.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = label("", "Title")
        self.sub = label("", "Muted")
        titles.addWidget(self.title)
        titles.addWidget(self.sub)
        hl.addLayout(titles, 1)
        self.chip_box = QHBoxLayout()
        hl.addLayout(self.chip_box)
        self.switch = Segmented([("resume", "Resume"), ("cover-letter", "Cover letter")], "resume")
        self.switch.changed.connect(self._pick_kind)
        hl.addWidget(self.switch)
        hl.addWidget(button("✕", "", self.close, "Close (Esc)"))
        lay.addWidget(head)

        self.flags = Banner()
        lay.addWidget(self.flags)
        self.fine = label("", "Ok")
        self.fine.setContentsMargins(18, 6, 18, 6)
        lay.addWidget(self.fine)

        self.stack = QStackedWidget()
        self.message = label("Loading…", "Muted")
        self.message.setAlignment(Qt.AlignCenter)
        self.doc = QPdfDocument(self)
        self.view = QPdfView()
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.stack.addWidget(self.message)
        self.stack.addWidget(self.view)
        lay.addWidget(self.stack, 1)

        foot = QWidget()
        foot.setObjectName("StatusBar")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(18, 10, 18, 10)
        fl.setSpacing(8)
        self.prev_btn = with_icon(button("Previous", "", self.prev, "Previous (←)"), "chevron-left")
        self.next_btn = button("Skip  ▶", "", self.skip, "Next without deciding (→)")
        fl.addWidget(self.prev_btn)
        fl.addWidget(self.next_btn)
        fl.addStretch(1)
        self.tally = label("", "Muted")
        fl.addWidget(self.tally)
        fl.addSpacing(12)
        self.delete_btn = button("Delete Resume", "", self.delete, "Delete this Resume (asks first)")
        self.remake_btn = with_icon(button("Remake", "", self.remake, "Make it again, first in the queue (R)"), "refresh")
        self.ok_btn = with_icon(button("Looks fine", "Primary", self.accept_one,
                                       "Pass this Resume and letter from now on (A)"), "check", "accent_fg")
        for btn in (self.delete_btn, self.remake_btn, self.ok_btn):
            btn.setMinimumHeight(38)
            fl.addWidget(btn)
        lay.addWidget(foot)

        for key, slot in (("Left", self.prev), ("Right", self.skip), ("A", self.accept_one), ("R", self.remake)):
            QShortcut(QKeySequence(key), self, activated=slot)

        self._show()

    # -------------------------------------------------------------- showing
    @property
    def bid(self) -> dict:
        return self.bids[self.index]

    def _show(self) -> None:
        if not self.bids:
            self.title.setText("Nothing to review")
            self._message("Nothing to review here.")
            for btn in (self.prev_btn, self.next_btn, self.delete_btn, self.remake_btn, self.ok_btn):
                btn.setEnabled(False)
            return
        bid = self.bid
        self.progress.setText(f"{self.index + 1} / {len(self.bids)}")
        self.title.setText(str(bid.get("company", "")))
        who = (bid.get("candidate") or {}).get("displayName") or ""
        self.sub.setText(" · ".join(x for x in (f"#{bid.get('number', '')}", bid.get("role", ""), who) if x))
        while self.chip_box.count():
            w = self.chip_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        decided = self.decisions.get(bid["id"])
        if decided:
            text, kind = DECISION[decided]
            self.chip_box.addWidget(Chip(text, kind))
        elif bid.get("remakeRequested"):
            self.chip_box.addWidget(Chip("Remake queued", "interview"))
        check = bid.get("resumeCheck") or {}
        reasons = resume_actions.reasons_of(bid)
        self.flags.show_text(resume_actions.reasons_tip(reasons))
        if not reasons:
            self.fine.setText("✓  The check found nothing wrong." if check.get("status") == "ok"
                              else "Not checked yet — look it over yourself.")
            self.fine.setObjectName("Ok" if check.get("status") == "ok" else "Muted")
        self.fine.setVisible(not reasons)
        self.fine.style().unpolish(self.fine)
        self.fine.style().polish(self.fine)
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.bids) - 1)
        gone = decided == "deleted"
        self.ok_btn.setEnabled(not gone and bool(bid.get("hasResume", True)))
        self.remake_btn.setEnabled(not gone and decided != "remake" and not bid.get("remakeRequested"))
        self.delete_btn.setEnabled(not gone)
        counts = {k: sum(1 for v in self.decisions.values() if v == k) for k in DECISION}
        self.tally.setText(f"✓ {counts['ok']}   ↻ {counts['remake']}   ✕ {counts['deleted']}")
        has_letter = bool(bid.get("hasCoverLetter"))
        self.switch.buttons["cover-letter"].setEnabled(has_letter)
        if self.kind == "cover-letter" and not has_letter:
            self.kind = "resume"
        self.switch.set_current(self.kind)
        self._load(self.kind)
        self._prefetch()

    def _pick_kind(self, kind: str) -> None:
        self.kind = kind
        self._load(kind)

    def _profile(self, bid: dict) -> str | None:
        return (bid.get("candidate") or {}).get("profileId") or self.state.request_profile

    def _load(self, kind: str) -> None:
        bid = self.bid
        if self.decisions.get(bid["id"]) == "deleted":
            self._message("Deleted.")
            return
        key = (bid["id"], kind)
        if key in self._cache:
            self._pdf(self._cache[key])
            return
        self._message("Loading…")
        self._fetch(bid, kind, show=True)

    def _fetch(self, bid: dict, kind: str, show: bool) -> None:
        key = (bid["id"], kind)
        profile = self._profile(bid)

        def done(result, k=key):
            self._cache[k] = result[0]
            if show and self.bids and k == (self.bid["id"], self.kind):
                self._pdf(result[0])

        def failed(error, k=key):
            if show and self.bids and k == (self.bid["id"], self.kind):
                self._message(_message(error))

        tasks.run(lambda: self.state.api.document(bid["id"], kind, "pdf", profile), done, failed, owner=self)

    def _prefetch(self) -> None:
        if self.index + 1 < len(self.bids):
            nxt = self.bids[self.index + 1]
            if (nxt["id"], "resume") not in self._cache:
                self._fetch(nxt, "resume", show=False)

    def _pdf(self, data: bytes) -> None:
        self.doc.close()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.ReadOnly)
        self._buffer = buffer
        self.doc.load(buffer)
        if self.doc.status() == QPdfDocument.Status.Error:
            self._message("The PDF could not be shown.")
            return
        self.stack.setCurrentIndex(1)

    def _message(self, text: str) -> None:
        self.message.setText(text)
        self.stack.setCurrentIndex(0)

    # -------------------------------------------------------------- moving and deciding
    def prev(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.kind = "resume"
            self._show()

    def _advance(self) -> None:
        if self.index < len(self.bids) - 1:
            self.index += 1
            self.kind = "resume"
            self._show()
        else:
            self._show()
            counts = {k: sum(1 for v in self.decisions.values() if v == k) for k in DECISION}
            QMessageBox.information(self, "Review finished",
                                    f"That was the last one.\n\nLooks fine: {counts['ok']}\nRemake: {counts['remake']}\n"
                                    f"Deleted: {counts['deleted']}")

    def skip(self) -> None:
        if self.bids and self.bid["id"] not in self.decisions:
            self.decisions[self.bid["id"]] = "skip"
        self._advance()

    def _decided(self, decision: str) -> None:
        self._busy = False
        self.decisions[self.bid["id"]] = decision
        self._advance()

    def _failed(self, title: str, error: Exception) -> None:
        self._busy = False
        QMessageBox.warning(self, title, _message(error))

    def accept_one(self) -> None:
        if self._busy or not self.bids or not self.ok_btn.isEnabled():
            return
        self._busy = True
        bid = self.bid
        profile = resume_actions.bid_profile(self.state, bid)

        def done(result):
            bid["resumeCheck"] = (result or {}).get("check") or bid.get("resumeCheck")
            self._decided("ok")

        tasks.run(lambda: self.state.api.request("POST", f"/api/resume-check/bids/{bid['id']}/accept", profile_id=profile),
                  done, lambda e: self._failed("Looks fine", e), owner=self)

    def remake(self) -> None:
        if self._busy or not self.bids or not self.remake_btn.isEnabled():
            return
        self._busy = True
        bid = self.bid
        body = {"ids": [bid["id"]]}
        profile = resume_actions.bid_profile(self.state, bid)

        def done(_r):
            bid["remakeRequested"] = True
            self._decided("remake")

        tasks.run(lambda: self.state.api.request("POST", "/api/resume-check/remake", json_body=body, profile_id=profile),
                  done, lambda e: self._failed("Remake", e), owner=self)

    def delete(self) -> None:
        if self._busy or not self.bids:
            return
        bid = self.bid
        if QMessageBox.question(self, "Delete Resume",
                                f"Delete the Resume of {bid.get('company', '')} (#{bid.get('number', '')})?\n\n"
                                "Its PDF and Word files are deleted. Remake makes a new one.") != QMessageBox.Yes:
            return
        self._busy = True
        profile = resume_actions.bid_profile(self.state, bid)

        def done(_r):
            bid["hasResume"] = False
            self._decided("deleted")

        tasks.run(lambda: self.state.api.request("DELETE", f"/api/bids/{bid['id']}/resume", profile_id=profile),
                  done, lambda e: self._failed("Delete Resume", e), owner=self)

    def done(self, result: int) -> None:  # noqa: D401 - QDialog.done
        if self.decisions:
            self.state.data_changed.emit()
            if any(v == "remake" for v in self.decisions.values()):
                resume_actions._offer_start(self.parentWidget() or self, self.state)
        super().done(result)


def load_bids(state: AppState, query: dict, limit: int = 2000) -> list[dict]:
    """Every application matching an Applications-tab query (page by page, up to `limit`)."""
    api = state.api
    profile = state.request_profile
    out: list[dict] = []
    page = 1
    while len(out) < limit:
        params = {"page": page, "pageSize": 100, "sort": "number"}
        if query.get("statuses"):
            params["statuses"] = ",".join(query["statuses"])
        for key in ("hasResume", "needsRemake"):
            if query.get(key):
                params[key] = query[key]
        if profile and api.session.mode == "account":
            params["profileId"] = profile
        data = api.request("GET", "/api/bids", params=params, profile_id=profile) or {}
        out.extend(data.get("items", []))
        if page >= int(data.get("totalPages", 1)):
            break
        page += 1
    return [b for b in out if b.get("hasResume")]


def open_review(parent: QWidget, state: AppState, query: dict, title: str) -> None:
    """Load the applications for `query` and open the review at the first one."""
    def done(bids: list[dict]):
        if not bids:
            QMessageBox.information(parent, title, "There is no Resume to review here.")
            return
        ReviewDialog(state, bids, 0, parent, title).exec()

    tasks.run(lambda: load_bids(state, query), done,
              lambda e: QMessageBox.warning(parent, title, _message(e)), owner=parent)
