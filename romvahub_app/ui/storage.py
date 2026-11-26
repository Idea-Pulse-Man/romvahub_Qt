"""Storage: the Resume folder on the server, "Make files", and (Super Admin) the database's size,
"Backup and remove" and "Restore from backup".

The server keeps each Resume and cover letter as JSON; their Word and PDF files are copies in the
Resume folder, made again from the JSON whenever one is missing. See the backend's
src/resume/store/ and src/admin/storage.service.ts.
"""

from __future__ import annotations

import html
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QInputDialog,
    QMessageBox, QProgressBar, QProgressDialog, QVBoxLayout, QWidget,
)

from .. import tasks
from ..state import ALL, AppState
from ..statuses import STATUSES
from .admin import _Page, _boxed, _dialog, _item, _message, _ok_cancel, _table, _when
from .widgets import Card, button, label


def _size(n: int | float | None) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def range_dialog(parent: QWidget, state: AppState, title: str, ok_text: str, intro: str,
                 default_statuses: list[str]) -> dict | None:
    """From – To dates (the application's date), one or more statuses, and a Profile."""
    dlg, lay = _dialog(parent, title, 560)
    lay.addWidget(label(intro, "Muted", wrap=True))
    form = QFormLayout()
    form.setVerticalSpacing(10)
    today = date.today()
    start = QDateEdit(QDate(today - timedelta(days=30)))
    end = QDateEdit(QDate(today))
    for edit in (start, end):
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
    dates = QHBoxLayout()
    dates.addWidget(label("From"))
    dates.addWidget(start)
    dates.addSpacing(12)
    dates.addWidget(label("To"))
    dates.addWidget(end)
    dates.addStretch(1)
    form.addRow("Dates", dates)

    profile = QComboBox()
    if state.can_pick_all():
        profile.addItem("All Profiles", None)
    for p in state.profiles:
        if not p.get("revoked"):
            profile.addItem(p.get("name") or "Profile", p.get("id"))
    if state.profile_id and state.profile_id != ALL:
        index = profile.findData(state.profile_id)
        if index >= 0:
            profile.setCurrentIndex(index)
    form.addRow("Profile", profile)
    lay.addLayout(form)

    lay.addWidget(label("Statuses", "FieldLabel"))
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    boxes: dict[str, QCheckBox] = {}
    for i, status in enumerate(STATUSES):
        box = QCheckBox(status)
        box.setChecked(status in default_statuses)
        boxes[status] = box
        grid.addWidget(box, i // 3, i % 3)
    lay.addLayout(grid)
    error = label("", "Error", wrap=True)
    error.hide()
    lay.addWidget(error)
    buttons = _ok_cancel(dlg, lay, ok_text)
    result: dict = {}

    def accept() -> None:
        statuses = [s for s, box in boxes.items() if box.isChecked()]
        if not statuses:
            error.setText("Choose at least one status.")
            error.show()
            return
        if start.date() > end.date():
            error.setText('"From" must not be after "To".')
            error.show()
            return
        result.update({"from": start.date().toString("yyyy-MM-dd"), "to": end.date().toString("yyyy-MM-dd"),
                       "statuses": statuses})
        if profile.currentData():
            result["profileId"] = profile.currentData()
        dlg.accept()

    buttons.accepted.connect(accept)
    return result if dlg.exec() == QDialog.Accepted else None


def make_files(parent: QWidget, state: AppState) -> None:
    """"Make files": the Word and PDF copies of the applications in a date range and statuses, made on the
    server from their JSON. Copies of an application whose status keeps none are deleted after 3 days."""
    choice = range_dialog(
        parent, state, "Make files", "Make files",
        "Makes the Resume and cover letter files (Word and PDF) on the server for these applications, from their "
        "saved JSON. Files of Applied (after 20 days), Skip, Failed, Expired and Other applications are deleted "
        "again after 3 days.",
        ["Applied"])
    if not choice:
        return

    def started(run: dict) -> None:
        total = int(run.get("total") or 0)
        if total == 0:
            QMessageBox.information(parent, "Make files", "No application in these dates and statuses has a Resume "
                                                          "or cover letter to make files from.")
            return
        progress = QProgressDialog(f"Making the files of {total} applications…", "Hide", 0, total, parent)
        progress.setWindowTitle("Make files")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        timer = QTimer(progress)

        def poll() -> None:
            tasks.run(lambda: state.api.request("GET", f"/api/resume-files/make/{run['id']}"), shown, lambda _e: None,
                      owner=progress)

        def shown(now: dict) -> None:
            done = int(now.get("done") or 0) + int(now.get("failed") or 0)
            progress.setValue(min(done, total))
            if now.get("finishedAt"):
                timer.stop()
                progress.close()
                failed = int(now.get("failed") or 0)
                QMessageBox.information(parent, "Make files", f"Done: {now.get('done')} made"
                                        + (f", {failed} could not be made." if failed else "."))

        timer.timeout.connect(poll)
        timer.start(2000)
        progress.canceled.connect(timer.stop)

    tasks.run(lambda: state.api.request("POST", "/api/resume-files/make", json_body=choice), started,
              lambda e: QMessageBox.warning(parent, "Make files", _message(e)), owner=parent)


class StoragePage(_Page):
    """Admins: the Resume folder and "Make files". The Super Admin also: the database's size, backups."""

    BACKUP_HEADERS = ["Made", "Dates", "Statuses", "Applications", "Size", "Removed", "Put back"]

    def __init__(self, state: AppState):
        super().__init__(state, "Storage", "Where the server keeps the Resume files, and how full the database is.")
        # --- Resume folder
        folder_card = Card()
        folder_lay = QVBoxLayout(folder_card)
        folder_lay.setContentsMargins(16, 14, 16, 14)
        folder_lay.addWidget(label("Resume folder", "SectionTitle"))
        folder_lay.addWidget(label("The server keeps every Resume and cover letter as JSON in the database. Their Word "
                                   "and PDF files are copies in this folder on the server, made again from the JSON "
                                   "whenever one is missing — so moving the server needs the database only.",
                                   "Muted", wrap=True))
        self.folder_text = label("…", wrap=True)
        self.folder_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        folder_lay.addWidget(self.folder_text)
        row = QHBoxLayout()
        row.addWidget(button("Change folder…", "", self._change_folder, "A full path on the server"))
        row.addWidget(button("Use the default", "", lambda: self._set_folder(None)))
        row.addWidget(button("Clean up now", "", self._clean_up, "Apply the file rules now instead of tonight"))
        row.addStretch(1)
        row.addWidget(button("Make files…", "Primary", lambda: make_files(self, self.state)))
        folder_lay.addLayout(row)
        self.lay.addWidget(folder_card)

        # --- Database (Super Admin)
        self.db_card = Card()
        db_lay = QVBoxLayout(self.db_card)
        db_lay.setContentsMargins(16, 14, 16, 14)
        db_lay.addWidget(label("Database", "SectionTitle"))
        self.db_bar = QProgressBar()
        self.db_bar.setTextVisible(True)
        db_lay.addWidget(self.db_bar)
        self.db_text = label("", "Muted", wrap=True)
        db_lay.addWidget(self.db_text)
        actions = QHBoxLayout()
        actions.addWidget(button("Backup and remove…", "Primary", self._backup,
                                 "Save to a .zip, then remove from the database"))
        actions.addWidget(button("Restore from backup…", "", self._restore))
        self.remove_btn = button("Remove the chosen backup…", "", self._remove_chosen,
                                 "For a backup saved but not yet removed")
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        db_lay.addLayout(actions)
        self.backups = _table(self.BACKUP_HEADERS)
        self.backups.itemSelectionChanged.connect(self._backup_selection)
        db_lay.addWidget(_boxed(self.backups), 1)
        self.lay.addWidget(self.db_card, 1)
        self.db_card.setVisible(state.session.is_super_admin)
        self.backup_rows: list[dict] = []
        self._backup_selection()
        if not state.session.is_super_admin:
            self.lay.addStretch(1)

    # ------------------------------------------------------------------ load
    def reload(self) -> None:
        self.set_error("")
        tasks.run(lambda: self.state.api.request("GET", "/api/resume-files/folder"), self._show_folder, self.failed,
                  owner=self)
        if self.state.session.is_super_admin:
            tasks.run(lambda: self.state.api.request("GET", "/api/admin/storage"), self._show_storage, self.failed,
                      owner=self)

    def _show_folder(self, info: dict) -> None:
        usage = info.get("usage") or {}
        default = " (the default)" if info.get("isDefault") else ""
        more = "" if usage.get("complete", True) else "+"
        self._folder = str(info.get('folder') or '')
        self.folder_text.setText(f"<b>{html.escape(self._folder)}</b>{default}<br>"
                                 f"{usage.get('files', 0)}{more} files, {_size(usage.get('bytes'))}")

    def _show_storage(self, data: dict) -> None:
        db = data.get("database") or {}
        used, limit = int(db.get("bytes") or 0), int(db.get("limitBytes") or 1)
        self.db_bar.setRange(0, 1000)
        self.db_bar.setValue(min(1000, int(used * 1000 / limit)))
        self.db_bar.setFormat(f"{_size(used)} of {_size(limit)}  ({used * 100 / limit:.0f}%)")
        tables = ", ".join(f"{t['name']} {_size(t['bytes'])}" for t in (db.get("tables") or [])[:5])
        self.db_text.setText(f"{data.get('applications', 0)} applications, {data.get('inBackup', 0)} of them in a "
                             f"backup. Biggest tables: {tables}.")
        self.backup_rows = list(data.get("backups") or [])
        t = self.backups
        t.setRowCount(len(self.backup_rows))
        for r, b in enumerate(self.backup_rows):
            f = b.get("filter") or {}
            t.setItem(r, 0, _item(_when(b.get("createdAt")), b.get("id")))
            t.setItem(r, 1, _item(f"{f.get('from', '')} – {f.get('to', '')}"))
            t.setItem(r, 2, _item(", ".join(f.get("statuses") or []), muted=True))
            t.setItem(r, 3, _item(str(b.get("applications", 0))))
            t.setItem(r, 4, _item(_size(b.get("size")), muted=True))
            t.setItem(r, 5, _item(_when(b.get("removedAt")) if b.get("removedAt") else "Not yet",
                                  muted=not b.get("removedAt")))
            t.setItem(r, 6, _item(_when(b.get("restoredAt")) if b.get("restoredAt") else "—", muted=True))
        self._backup_selection()

    # ------------------------------------------------------------------ Resume folder
    def _change_folder(self) -> None:
        current = getattr(self, "_folder", "")
        path, ok = QInputDialog.getText(self, "Resume folder", "A full path on the server (for example "
                                        "C:\\romva\\files). Its kept\\ folder moves along.", text=current)
        if ok and path.strip():
            self._set_folder(path.strip())

    def _set_folder(self, path: str | None) -> None:
        tasks.run(lambda: self.state.api.request("PUT", "/api/resume-files/folder", json_body={"folder": path}),
                  lambda _info: self.reload(), lambda e: QMessageBox.warning(self, "Resume folder", _message(e)),
                  owner=self)

    def _clean_up(self) -> None:
        tasks.run(lambda: self.state.api.request("POST", "/api/resume-files/clean-up", timeout=600),
                  lambda r: (QMessageBox.information(self, "Clean up", f"{r.get('deleted', 0)} copies deleted "
                                                     f"(of {r.get('applications', 0)} applications with files)."),
                             self.reload()),
                  lambda e: QMessageBox.warning(self, "Clean up", _message(e)), owner=self)

    # ------------------------------------------------------------------ Backup and remove
    def _backup(self) -> None:
        choice = range_dialog(
            self, self.state, "Backup and remove", "Make the backup",
            "First the job description, Resume, cover letter and application chat of these applications are saved "
            "to a .zip on this computer. Only then, if you say so, are they removed from the database. Company, role, "
            "status and dates stay.",
            ["Applied", "Failed", "Expired", "Skip"])
        if not choice:
            return
        self.set_error("")

        def got(response) -> None:
            backup_id = response.headers.get("x-backup-id", "")
            count = response.headers.get("x-backup-count", "?")
            from ..api import _filename
            name = _filename(response.headers.get("content-disposition", "")) or "romva-backup.zip"
            path, _ = QFileDialog.getSaveFileName(self, "Save the backup", str(Path.home() / "Documents" / name),
                                                  "Backup (*.zip)")
            if not path:
                QMessageBox.information(self, "Backup", "The backup was not saved, so nothing will be removed.")
                self.reload()
                return
            Path(path).write_bytes(response.content)
            if Path(path).stat().st_size != len(response.content):
                QMessageBox.warning(self, "Backup", "The backup file could not be written completely. Nothing was "
                                                    "removed.")
                return
            self._ask_remove(backup_id, count, path)

        tasks.run(lambda: self.state.api.request("POST", "/api/admin/storage/backup", json_body=choice, raw=True,
                                                 timeout=900),
                  got, lambda e: QMessageBox.warning(self, "Backup", _message(e)), owner=self)

    def _ask_remove(self, backup_id: str, count, path: str) -> None:
        answer = QMessageBox.question(
            self, "Remove from the database?",
            f"The backup of {count} applications is saved:\n{path}\n\n"
            "Remove their job description, Resume, cover letter and application chat from the database now?\n"
            "Company, role, status and dates stay. The applications table pauses for a few seconds while the space "
            "is given back.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            QMessageBox.information(self, "Backup", "Nothing was removed. You can remove it later: choose the backup "
                                                    "in the list, then “Remove the chosen backup…”.")
            self.reload()
            return
        self._remove(backup_id)

    def _remove(self, backup_id: str) -> None:
        def done(r: dict) -> None:
            skipped = int(r.get("changedSinceBackup") or 0)
            QMessageBox.information(
                self, "Removed",
                f"Removed from {r.get('removed', 0)} applications. The database went from "
                f"{_size(r.get('databaseBytesBefore'))} to {_size(r.get('databaseBytesAfter'))}."
                + (f"\n\n{skipped} changed after the backup was made, so they were left as they are." if skipped else "")
                + ("" if r.get("compacted", True) else "\n\nThe space could not be given back yet; it is reused."))
            self.reload()

        tasks.run(lambda: self.state.api.request("POST", f"/api/admin/storage/backups/{backup_id}/remove",
                                                 timeout=900),
                  done, lambda e: QMessageBox.warning(self, "Remove", _message(e)), owner=self)

    def _chosen_backup(self) -> dict | None:
        row = self.backups.currentRow()
        if row < 0 or not self.backups.selectionModel().hasSelection():
            return None
        bid = self.backups.item(row, 0).data(Qt.UserRole)
        return next((b for b in self.backup_rows if b.get("id") == bid), None)

    def _backup_selection(self) -> None:
        chosen = self._chosen_backup()
        self.remove_btn.setEnabled(bool(chosen) and not chosen.get("removedAt"))

    def _remove_chosen(self) -> None:
        chosen = self._chosen_backup()
        if chosen and not chosen.get("removedAt"):
            self._ask_remove(chosen["id"], chosen.get("applications", "?"), "(saved earlier)")

    # ------------------------------------------------------------------ Restore
    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from backup", str(Path.home() / "Documents"),
                                              "Backup (*.zip)")
        if not path:
            return
        data = Path(path).read_bytes()
        files = lambda: {"backup": (Path(path).name, data, "application/zip")}  # noqa: E731

        def counted(r: dict) -> None:
            if not r.get("restorable"):
                QMessageBox.information(self, "Restore", f"The file holds {r.get('inFile', 0)} applications, but none "
                                                         "of them is waiting in a backup. Nothing to put back.")
                return
            answer = QMessageBox.question(self, "Restore",
                                          f"The file holds {r.get('inFile', 0)} applications; {r.get('restorable')} "
                                          "can be put back. Put them back now?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return
            tasks.run(lambda: self.state.api.request("POST", "/api/admin/storage/restore", files=files(), timeout=900),
                      lambda done: (QMessageBox.information(self, "Restore", f"Put back: {done.get('restored', 0)}."),
                                    self.reload()),
                      lambda e: QMessageBox.warning(self, "Restore", _message(e)), owner=self)

        tasks.run(lambda: self.state.api.request("POST", "/api/admin/storage/restore", params={"dryRun": "true"},
                                                 files=files(), timeout=900),
                  counted, lambda e: QMessageBox.warning(self, "Restore", _message(e)), owner=self)
