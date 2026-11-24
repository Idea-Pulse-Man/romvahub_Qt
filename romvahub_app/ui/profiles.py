"""Profiles: the bidder edits the Profiles they work on (the admin: any Profile).

Bidders may edit personal and contact details, links, work experience,
education, job-form and EEO answers, the resume and cover letter prompts, the
Avoid lists and the template. Creating or deleting a Profile, who may use it,
tokens and the global AI settings stay with the admin (website).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from .. import tasks
from ..state import AppState
from .widgets import button, label, page_header

TEXT_FIELDS = {
    "Personal": [("firstName", "First name"), ("middleName", "Middle name"), ("lastName", "Last name"),
                 ("preferredFirstName", "Preferred first name"), ("preferredLastName", "Preferred last name"),
                 ("dateOfBirth", "Date of birth (YYYY-MM-DD)"), ("birthYear", "Birth year")],
    "Contact": [("email", "Email"), ("phone", "Phone"), ("location", "Location (shown on the resume)"),
                ("addressLine", "Address"), ("city", "City"), ("state", "State"), ("zipCode", "ZIP"),
                ("county", "County"), ("country", "Country"), ("timezone", "Timezone")],
    "Links": [("linkedinUrl", "LinkedIn"), ("githubUrl", "GitHub"), ("portfolioUrl", "Portfolio"), ("otherUrl", "Other")],
    "Job answers": [("authorizedCountries", "Authorized to work in (comma-separated)"),
                    ("securityClearance", "Security clearance"), ("drugTestWillingness", "Drug test"),
                    ("noticePeriod", "Notice period"), ("openToRelocation", "Open to relocation"),
                    ("inPersonAvailability", "In-person availability"), ("requireAccommodations", "Needs accommodations")],
    "EEO": [("gender", "Gender"), ("ethnicity", "Ethnicity"), ("disabilityStatus", "Disability"),
            ("veteranStatus", "Veteran status"), ("lgbtqIdentity", "LGBTQ+")],
}
EXPERIENCE_COLS = [("company", "Company"), ("title", "Title"), ("location", "Location"), ("startDate", "Start (YYYY-MM)"),
                   ("endDate", "End (YYYY-MM, empty = now)")]
EDUCATION_COLS = [("degree", "Degree"), ("major", "Major"), ("university", "University"), ("location", "Location"),
                  ("startDate", "Start (YYYY-MM)"), ("endDate", "End (YYYY-MM)")]


class ProfilesPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.current: str | None = None
        self.detail: dict = {}
        self.fields: dict[str, QLineEdit] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)
        lay.addWidget(page_header("Profiles", "Edit the Profiles you work on. Creating, deleting and sharing Profiles "
                                              "is done by your admin."))
        row = QHBoxLayout()
        row.setSpacing(16)
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.currentItemChanged.connect(self._picked)
        row.addWidget(self.list)

        right = QVBoxLayout()
        head = QHBoxLayout()
        self.name = label("", "Title")
        head.addWidget(self.name, 1)
        self.saved = label("", "Ok")
        head.addWidget(self.saved)
        self.save_btn = button("Save", "Primary", self._save)
        head.addWidget(self.save_btn)
        right.addLayout(head)
        self.error = label("", "Error", wrap=True)
        self.error.hide()
        right.addWidget(self.error)

        self.tabs = QTabWidget()
        for tab, fields in TEXT_FIELDS.items():
            self.tabs.addTab(self._form(fields, preferred=(tab == "Personal")), tab)
        self.experience = self._table(EXPERIENCE_COLS)
        self.tabs.insertTab(3, self._table_page(self.experience, "Add job"), "Experience")
        self.education = self._table(EDUCATION_COLS)
        self.tabs.insertTab(4, self._table_page(self.education, "Add school"), "Education")
        self.tabs.addTab(self._prompts_page(), "Resume prompts")
        self.tabs.addTab(self._avoid_page(), "Avoid lists")
        right.addWidget(self.tabs, 1)
        row.addLayout(right, 1)
        lay.addLayout(row, 1)

        state.profiles_changed.connect(self._fill)
        self._fill()

    # ------------------------------------------------------------------ building
    def _form(self, fields, preferred: bool = False) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(16, 16, 16, 16)
        form.setVerticalSpacing(10)
        if preferred:
            self.has_preferred = QCheckBox("Uses a preferred name")
            form.addRow("", self.has_preferred)
        for key, text in fields:
            edit = QLineEdit()
            self.fields[key] = edit
            form.addRow(text, edit)
        scroll.setWidget(inner)
        return scroll

    def _table(self, cols) -> QTableWidget:
        table = QTableWidget(0, len(cols))
        table.setHorizontalHeaderLabels([text for _k, text in cols])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.cols = cols  # type: ignore[attr-defined]
        return table

    def _table_page(self, table: QTableWidget, add_text: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(table, 1)
        row = QHBoxLayout()
        row.addWidget(button(f"+ {add_text}", "", lambda: table.insertRow(table.rowCount())))
        row.addWidget(button("Remove selected", "", lambda: [table.removeRow(r) for r in sorted({i.row() for i in table.selectedIndexes()}, reverse=True)]))
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _prompts_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(label("Resume template", "Label"))
        self.template = QComboBox()
        lay.addWidget(self.template)
        lay.addWidget(label("Resume prompt (what the AI is asked for the resume)", "Label"))
        self.resume_prompt = QPlainTextEdit()
        lay.addWidget(self.resume_prompt, 2)
        lay.addWidget(label("Cover letter prompt (empty = no cover letter)", "Label"))
        self.cover_prompt = QPlainTextEdit()
        lay.addWidget(self.cover_prompt, 1)
        return page

    def _avoid_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(label("Roles to skip (one per line)", "Label"))
        self.avoid_roles = QPlainTextEdit()
        lay.addWidget(self.avoid_roles)
        lay.addWidget(label("Companies to skip (one per line)", "Label"))
        self.avoid_companies = QPlainTextEdit()
        lay.addWidget(self.avoid_companies)
        lay.addWidget(label("The scraper doesn't save jobs that match these.", "Muted"))
        return page

    # ------------------------------------------------------------------ data
    def _fill(self) -> None:
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.state.profiles:
            item = QListWidgetItem(p["name"] + ("   (revoked)" if p.get("revoked") else ""))
            item.setData(Qt.UserRole, p["id"])
            if p.get("revoked"):
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.list.addItem(item)
        self.list.blockSignals(False)
        target = keep or self.state.profile_id or next((p["id"] for p in self.state.profiles if not p.get("revoked")), None)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == target:
                self.list.setCurrentRow(i)
                return
        if self.list.count():
            self.list.setCurrentRow(0)

    def _picked(self, item: QListWidgetItem | None, _prev=None) -> None:
        if not item:
            return
        self.current = item.data(Qt.UserRole)
        self.name.setText(item.text())
        self.saved.setText("")
        self._set_error("")
        self.save_btn.setEnabled(False)
        api, pid, admin = self.state.api, self.current, self.state.session.is_admin

        def fetch():
            detail = api.request("GET", f"/api/admin/profiles/{pid}") if admin else api.profile_detail(pid)
            prompts = api.prompts(pid)
            avoid = api.avoid(pid)
            return detail, prompts, avoid

        tasks.run(fetch, lambda r, p=pid: self._show(p, *r), lambda e: self._set_error(getattr(e, "message", str(e))), owner=self)

    def _show(self, pid: str, detail: dict, prompts: dict, avoid: dict) -> None:
        if pid != self.current:
            return
        self.detail = detail or {}
        for key, edit in self.fields.items():
            value = self.detail.get(key, "")
            edit.setText(", ".join(value) if isinstance(value, list) else str(value or ""))
        self.has_preferred.setChecked(bool(self.detail.get("hasPreferredName")))
        _fill_table(self.experience, self.detail.get("workExperience") or [])
        _fill_table(self.education, self.detail.get("education") or [])
        self.template.clear()
        for t in (prompts or {}).get("templates", []):
            self.template.addItem(t.get("name", t.get("id")), t.get("id"))
        index = self.template.findData((prompts or {}).get("resumeTemplateId"))
        if index >= 0:
            self.template.setCurrentIndex(index)
        self.resume_prompt.setPlainText((prompts or {}).get("resumePrompt") or "")
        self.cover_prompt.setPlainText((prompts or {}).get("coverLetterPrompt") or "")
        self.avoid_roles.setPlainText("\n".join((avoid or {}).get("avoidRoles", [])))
        self.avoid_companies.setPlainText("\n".join((avoid or {}).get("avoidCompanies", [])))
        self.save_btn.setEnabled(True)

    def _body(self) -> dict:
        keys = [k for fields in TEXT_FIELDS.values() for k, _t in fields]
        body = {k: self.detail.get(k) for k in ("resumeTemplateId",) if self.detail.get(k)}
        for key in keys:
            text = self.fields[key].text().strip()
            body[key] = [x.strip() for x in text.split(",") if x.strip()] if key == "authorizedCountries" else text
        body["hasPreferredName"] = self.has_preferred.isChecked()
        body["workExperience"] = _read_table(self.experience, self.detail.get("workExperience") or [])
        body["education"] = _read_table(self.education, self.detail.get("education") or [])
        if self.template.currentData():
            body["resumeTemplateId"] = self.template.currentData()
        return body

    def _save(self) -> None:
        if not self.current:
            return
        api, pid, admin = self.state.api, self.current, self.state.session.is_admin
        body = self._body()
        prompts = {
            "resumePrompt": self.resume_prompt.toPlainText().strip() or None,
            "coverLetterPrompt": self.cover_prompt.toPlainText().strip() or None,
        }
        if self.template.currentData():
            prompts["resumeTemplateId"] = self.template.currentData()
        avoid = {
            "avoidRoles": [x.strip() for x in self.avoid_roles.toPlainText().splitlines() if x.strip()],
            "avoidCompanies": [x.strip() for x in self.avoid_companies.toPlainText().splitlines() if x.strip()],
        }

        def run():
            if admin:
                detail = api.request("PUT", f"/api/admin/profiles/{pid}", json_body=body)
            else:
                detail = api.save_profile(pid, body)
            api.save_prompts(pid, prompts)
            api.save_avoid(pid, avoid)
            return detail

        self.save_btn.setEnabled(False)
        self.saved.setText("Saving…")

        def done(detail):
            self.save_btn.setEnabled(True)
            self.detail = detail or self.detail
            self.saved.setText("✓ Saved")
            self._set_error("")

        def failed(error):
            self.save_btn.setEnabled(True)
            self.saved.setText("")
            message = getattr(error, "message", str(error))
            if getattr(error, "status", 0) == 404 and not admin:
                message += ("\nYour server may not have the Profile editing update yet. Ask your admin to update the "
                            "backend.")
            self._set_error(message)

        tasks.run(run, done, failed, owner=self)

    def _set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))


def _fill_table(table: QTableWidget, rows: list[dict]) -> None:
    table.setRowCount(0)
    for row in rows:
        r = table.rowCount()
        table.insertRow(r)
        for c, (key, _t) in enumerate(table.cols):  # type: ignore[attr-defined]
            item = QTableWidgetItem(str(row.get(key) or ""))
            item.setData(Qt.UserRole, row.get("id"))
            table.setItem(r, c, item)


def _read_table(table: QTableWidget, original: list[dict]) -> list[dict]:
    out = []
    for r in range(table.rowCount()):
        entry = {}
        row_id = None
        for c, (key, _t) in enumerate(table.cols):  # type: ignore[attr-defined]
            item = table.item(r, c)
            text = item.text().strip() if item else ""
            if item and item.data(Qt.UserRole):
                row_id = item.data(Qt.UserRole)
            entry[key] = text
        if not any(entry.values()):
            continue
        if entry.get("endDate") == "":
            entry["endDate"] = None
        if row_id:
            entry["id"] = row_id
        out.append(entry)
    return out

