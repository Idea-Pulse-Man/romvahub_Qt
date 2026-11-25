"""The Resume / cover letter preview: the PDF on screen, PDF and Word downloads, and Remake / Delete."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QStandardPaths, Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from .. import tasks
from ..state import AppState
from . import resume_actions
from .widgets import Banner, Segmented, button, label

KINDS = {"resume": "Resume", "cover-letter": "Cover letter"}


class DocViewer(QDialog):
    def __init__(self, state: AppState, bid: dict, kind: str = "resume", parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.bid = bid
        self.kind = kind
        self.profile_id = (bid.get("candidate") or {}).get("profileId") or state.request_profile
        self.setWindowTitle(f"{bid.get('company', '')} — {KINDS[kind]}")
        self.resize(900, 900)
        self._buffer: QBuffer | None = None
        self._pdf_cache: dict[str, tuple[bytes, str]] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget()
        head.setObjectName("TopBar")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 12, 18, 12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label(str(bid.get("company", "")), "Title"))
        candidate = (bid.get("candidate") or {}).get("displayName") or state.profile_name
        titles.addWidget(label(f"{bid.get('role', '')} · Profile: {candidate}", "Muted"))
        hl.addLayout(titles, 1)
        self.switch = Segmented([("resume", "Resume"), ("cover-letter", "Cover letter")], kind)
        self.switch.changed.connect(self.show_kind)
        hl.addWidget(self.switch)
        hl.addWidget(button("⬇  PDF", "Primary", lambda: self.download("pdf")))
        hl.addWidget(button("⬇  Word (DOCX)", "", lambda: self.download("docx")))
        self.remake_btn = button("Remake", "", self._remake, "Make the Resume and cover letter again (the old ones "
                                                            "stay until the new ones are saved)")
        self.remake_btn.setEnabled(not bid.get("remakeRequested"))
        if bid.get("remakeRequested"):
            self.remake_btn.setText("Remake queued")
        hl.addWidget(self.remake_btn)
        self.delete_btn = button("Delete", "", self._delete, "Delete this document")
        hl.addWidget(self.delete_btn)
        hl.addWidget(button("✕", "", self.close, "Close"))
        lay.addWidget(head)
        self.flags = Banner()
        lay.addWidget(self.flags)

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
        fl.setContentsMargins(18, 8, 18, 8)
        made = str(bid.get("resumeMadeAt") or "")[:10]
        fl.addWidget(label(f"Made {made}" if made else "", "Muted"))
        fl.addStretch(1)
        fl.addWidget(label("This is the file you upload when applying.", "Muted"))
        lay.addWidget(foot)

        self.show_kind(kind)

    def _remake(self) -> None:
        def done(_n):
            self.remake_btn.setText("Remake queued")
            self.remake_btn.setEnabled(False)

        resume_actions.remake(self, self.state, bids=[self.bid], on_done=done)

    def _delete(self) -> None:
        resume_actions.delete_doc(self, self.state, self.bid, self.kind, self.close)

    def show_kind(self, kind: str) -> None:
        self.kind = kind
        self.switch.set_current(kind)
        reasons = resume_actions.reasons_of(self.bid, kind)
        self.flags.show_text(resume_actions.reasons_tip(reasons) if reasons else "")
        has = self.bid.get("hasResume", True) if kind == "resume" else self.bid.get("hasCoverLetter", True)
        self.delete_btn.setEnabled(bool(has))
        self.delete_btn.setText("Delete Resume" if kind == "resume" else "Delete letter")
        self.setWindowTitle(f"{self.bid.get('company', '')} — {KINDS[kind]}")
        if kind == "cover-letter" and not self.bid.get("hasCoverLetter", True):
            self._show_message("No cover letter was made for this application.")
            return
        cached = self._pdf_cache.get(kind)
        if cached:
            self._show_pdf(cached[0])
            return
        self._show_message("Loading…")
        bid_id = self.bid["id"]
        tasks.run(lambda: self.state.api.document(bid_id, kind, "pdf", self.profile_id),
                  lambda result, k=kind: self._loaded(k, result),
                  lambda e: self._show_message(getattr(e, "message", str(e))), owner=self)

    def _loaded(self, kind: str, result: tuple[bytes, str]) -> None:
        self._pdf_cache[kind] = result
        if kind == self.kind:
            self._show_pdf(result[0])

    def _show_pdf(self, data: bytes) -> None:
        self.doc.close()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.ReadOnly)
        self._buffer = buffer
        self.doc.load(buffer)
        if self.doc.status() == QPdfDocument.Status.Error:
            self._show_message("The PDF could not be shown. Download it instead.")
            return
        self.stack.setCurrentIndex(1)

    def _show_message(self, text: str) -> None:
        self.message.setText(text)
        self.stack.setCurrentIndex(0)

    def download(self, fmt: str) -> None:
        kind = self.kind
        bid_id = self.bid["id"]

        def save(result: tuple[bytes, str]) -> None:
            data, name = result
            folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
            path, _ = QFileDialog.getSaveFileName(self, "Save as", str(Path(folder) / name),
                                                  "PDF (*.pdf)" if fmt == "pdf" else "Word (*.docx)")
            if path:
                Path(path).write_bytes(data)

        cached = self._pdf_cache.get(kind) if fmt == "pdf" else None
        if cached:
            save(cached)
            return
        tasks.run(lambda: self.state.api.document(bid_id, kind, fmt, self.profile_id), save,
                  lambda e: self._show_message(getattr(e, "message", str(e))), owner=self)
