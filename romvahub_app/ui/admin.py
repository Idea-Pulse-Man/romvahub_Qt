"""Admin pages, inside the app (nothing opens the website): Users, Tokens, AI settings, Pipeline and Calendar.

Roles: Super Admin (an admin who also makes Profile tokens), Admin, and User,
who is a Bidder or a Caller. Any admin sets roles, but not their own and not
the Super Admin's (the server checks this too).
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QGuiApplication, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QLabel,
    QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import tasks, theme
from ..state import AppState
from ..statuses import GROUP_STARTS, INTERVIEW_STATUSES, KIND, STATUSES
from .widgets import Card, Chip, button, icon_button, label, page_header

# (label, role, kind) for the role picker.
ROLE_CHOICES = [("Admin", "admin", "bidder"), ("Bidder", "user", "bidder"), ("Caller", "user", "caller")]
ROLE_CHIP = {"Super Admin": "interview", "Admin": "ready", "Bidder": "applied", "Caller": "offer"}
AI_PROVIDERS = [("openai", "OpenAI"), ("anthropic", "Anthropic (Claude)"), ("gemini", "Google Gemini"),
                ("deepseek", "DeepSeek")]


def role_of(user: dict) -> str:
    """Super Admin, Admin, Bidder or Caller."""
    if user.get("role") == "admin":
        return "Super Admin" if user.get("superAdmin") else "Admin"
    return "Caller" if user.get("kind") == "caller" else "Bidder"


def _message(error: Exception) -> str:
    return getattr(error, "message", str(error))


def _when(value: str | None, with_time: bool = True) -> str:
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo:
            moment = moment.astimezone()
        return moment.strftime("%b %d, %Y %H:%M" if with_time else "%b %d, %Y")
    except ValueError:
        return value


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setShowGrid(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setWordWrap(False)
    table.verticalHeader().setDefaultSectionSize(48)
    hh = table.horizontalHeader()
    hh.setHighlightSections(False)
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setSectionResizeMode(QHeaderView.Stretch)
    return table


def _item(text: str, data=None, muted: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setToolTip(text)
    if data is not None:
        item.setData(Qt.UserRole, data)
    if muted:
        item.setForeground(QBrush(QColor(theme.colors()["muted"])))
    return item


def _chip_cell(text: str, kind: str) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(6, 0, 0, 0)
    lay.addWidget(Chip(text, kind))
    lay.addStretch(1)
    return box


def _boxed(widget: QWidget) -> QFrame:
    card = QFrame()
    card.setObjectName("TableCard")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(1, 1, 1, 1)
    lay.addWidget(widget)
    return card


class _Page(QWidget):
    """Header with a Refresh button, an error line, and `reload()` on first show."""

    def __init__(self, state: AppState, title: str, subtitle: str):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self._loaded_once = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 20, 24, 16)
        self.lay.setSpacing(14)
        self.head = QHBoxLayout()
        self.head.setSpacing(8)
        self.head.addWidget(page_header(title, subtitle), 1)
        self.head.addWidget(icon_button("refresh", "Refresh", self.reload), 0, Qt.AlignTop)
        self.lay.addLayout(self.head)
        self.error = label("", "Error", wrap=True)
        self.error.hide()
        self.lay.addWidget(self.error)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self.reload()

    def reload(self) -> None:  # pragma: no cover - overridden
        pass

    def set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def failed(self, error: Exception) -> None:
        self.state.report_error(error)
        self.set_error(_message(error))


def _dialog(parent: QWidget, title: str, width: int = 460) -> tuple[QDialog, QVBoxLayout]:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(width)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(12)
    return dlg, lay


def _ok_cancel(dlg: QDialog, lay: QVBoxLayout, ok_text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText(ok_text)
    buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    return buttons


# ============================================================================ Users
class UsersPage(_Page):
    HEADERS = ["Name", "Email", "Role", "Status", "Applications", "Last sign-in", "Where"]

    def __init__(self, state: AppState):
        super().__init__(state, "Users", "Sign-in accounts. Roles: Super Admin, Admin, and User (Bidder or Caller).")
        self.users: list[dict] = []
        self.head.addWidget(button("Add user", "Primary", self._add), 0, Qt.AlignTop)

        self.table = _table(self.HEADERS)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.itemSelectionChanged.connect(self._selection)
        self.lay.addWidget(_boxed(self.table), 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.edit_btn = button("Edit", "", self._edit)
        self.profiles_btn = button("Profiles…", "", self._profiles, "Which Profiles this user works on")
        self.history_btn = button("Sign-ins…", "", self._history)
        self.suspend_btn = button("Suspend", "", self._toggle_suspend)
        self.delete_btn = button("Delete", "", self._delete)
        for btn in (self.edit_btn, self.profiles_btn, self.history_btn, self.suspend_btn, self.delete_btn):
            actions.addWidget(btn)
        actions.addStretch(1)
        self.count = label("", "Muted")
        actions.addWidget(self.count)
        self.lay.addLayout(actions)
        self._selection()

    # -------------------------------------------------------------- data
    def reload(self) -> None:
        self.set_error("")
        tasks.run(lambda: self.state.api.request("GET", "/api/admin/users"), self._show, self.failed, owner=self)

    def _show(self, users: list[dict]) -> None:
        keep = self._current_id()
        self.users = list(users or [])
        t = self.table
        t.setRowCount(len(self.users))
        for r, u in enumerate(self.users):
            role = role_of(u)
            suspended = u.get("status") == "suspended"
            t.setItem(r, 0, _item(u.get("displayName") or u.get("email", ""), u.get("id")))
            t.setItem(r, 1, _item(u.get("email", ""), muted=True))
            t.setItem(r, 2, _item(""))
            t.setCellWidget(r, 2, _chip_cell(role, ROLE_CHIP[role]))
            t.setItem(r, 3, _item(""))
            t.setCellWidget(r, 3, _chip_cell("Suspended" if suspended else "Active", "failed" if suspended else "draft"))
            t.setItem(r, 4, _item(str(u.get("bidCount", 0))))
            t.setItem(r, 5, _item(_when(u.get("lastLoginAt")), muted=True))
            t.setItem(r, 6, _item(u.get("lastLoginLocation") or u.get("lastLoginIp") or "—", muted=True))
            if u.get("id") == keep:
                t.selectRow(r)
        counts: dict[str, int] = {}
        for u in self.users:
            counts[role_of(u)] = counts.get(role_of(u), 0) + 1
        self.count.setText("  ·  ".join(f"{counts[k]} {k}" for k in ROLE_CHIP if counts.get(k)))
        self._selection()

    def _current_id(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item and self.table.selectionModel().hasSelection() else None

    def _current(self) -> dict | None:
        uid = self._current_id()
        return next((u for u in self.users if u.get("id") == uid), None)

    def _is_me(self, user: dict) -> bool:
        return user.get("id") == (self.state.session.user or {}).get("id")

    def _selection(self) -> None:
        user = self._current()
        for btn in (self.edit_btn, self.profiles_btn, self.history_btn):
            btn.setEnabled(bool(user))
        plain = bool(user) and user.get("role") != "admin" and not self._is_me(user)
        self.suspend_btn.setEnabled(plain)
        self.delete_btn.setEnabled(plain)
        self.suspend_btn.setText("Reactivate" if user and user.get("status") == "suspended" else "Suspend")
        tip = "" if plain or not user else "Admins can't be suspended or deleted. Make them a Bidder or Caller first."
        self.suspend_btn.setToolTip(tip)
        self.delete_btn.setToolTip(tip)

    def _menu(self, pos) -> None:
        if not self._current():
            return
        menu = QMenu(self)
        for btn in (self.edit_btn, self.profiles_btn, self.history_btn, self.suspend_btn, self.delete_btn):
            action = menu.addAction(btn.text(), btn.click)
            action.setEnabled(btn.isEnabled())
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _run(self, fn, message: str = "") -> None:
        def done(_r):
            self.reload()
            if message:
                self.state.mark_online()

        tasks.run(fn, done, lambda e: QMessageBox.warning(self, "Users", _message(e)), owner=self)

    # -------------------------------------------------------------- actions
    def _user_form(self, user: dict | None) -> None:
        new = user is None
        dlg, lay = _dialog(self, "Add user" if new else f"Edit {user.get('email', '')}")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        email = QLineEdit("" if new else user.get("email", ""))
        form.addRow("Email", email)
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        password.setPlaceholderText("At least 12 characters" if new else "Leave empty to keep the password")
        form.addRow("Password", password)
        role = QComboBox()
        for text, r, k in ROLE_CHOICES:
            role.addItem(text, (r, k))
        current = "Bidder" if new else role_of(user)
        if current == "Super Admin":
            role.insertItem(0, "Super Admin", ("admin", "bidder"))
            role.setCurrentIndex(0)
            role.setEnabled(False)
            role.setToolTip("The Super Admin stays an admin.")
        else:
            role.setCurrentIndex(max(0, role.findText(current)))
        if not new and self._is_me(user):
            role.setEnabled(False)
            role.setToolTip("You can't change your own role.")
        form.addRow("Role", role)
        lay.addLayout(form)
        lay.addWidget(label("Admin: everything, on every Profile. Bidder and Caller: the Profiles you give them "
                            "(same access; Caller takes the interview calls).", "Muted", wrap=True))
        buttons = _ok_cancel(dlg, lay, "Add user" if new else "Save")

        def accept():
            mail = email.text().strip()
            if not mail:
                QMessageBox.warning(dlg, "Users", "Enter the email.")
                return
            if (new or password.text()) and len(password.text()) < 12:
                QMessageBox.warning(dlg, "Users", "The password must be at least 12 characters.")
                return
            r, k = role.currentData()
            if new:
                body = {"email": mail, "password": password.text(), "role": r, "kind": k}
                self._run(lambda: self.state.api.request("POST", "/api/admin/users", json_body=body))
            else:
                body = {}
                if mail != user.get("email"):
                    body["email"] = mail
                if password.text():
                    body["password"] = password.text()
                if role.isEnabled():
                    if r != user.get("role"):
                        body["role"] = r
                    if k != user.get("kind"):
                        body["kind"] = k
                if not body:
                    dlg.accept()
                    return
                uid = user["id"]
                self._run(lambda: self.state.api.request("PATCH", f"/api/admin/users/{uid}", json_body=body))
            dlg.accept()

        buttons.accepted.connect(accept)
        dlg.exec()

    def _add(self) -> None:
        self._user_form(None)

    def _edit(self) -> None:
        user = self._current()
        if user:
            self._user_form(user)

    def _toggle_suspend(self) -> None:
        user = self._current()
        if not user:
            return
        suspend = user.get("status") != "suspended"
        if suspend and QMessageBox.question(
                self, "Suspend", f"Suspend {user.get('email')}? They are signed out and can't sign in until "
                                 "you reactivate them.") != QMessageBox.Yes:
            return
        body = {"status": "suspended" if suspend else "active"}
        uid = user["id"]
        self._run(lambda: self.state.api.request("PATCH", f"/api/admin/users/{uid}", json_body=body))

    def _delete(self) -> None:
        user = self._current()
        if not user:
            return
        text, ok = _confirm_text(self, "Delete user",
                                 f"This deletes {user.get('email')} and every application filed under the account. "
                                 "It can't be undone.\n\nType the email to confirm:")
        if not ok:
            return
        if text.strip().lower() != str(user.get("email", "")).lower():
            QMessageBox.information(self, "Delete user", "The email didn't match. Nothing was deleted.")
            return
        uid = user["id"]
        self._run(lambda: self.state.api.request("DELETE", f"/api/admin/users/{uid}"))

    def _profiles(self) -> None:
        user = self._current()
        if not user:
            return
        api, uid = self.state.api, user["id"]

        def fetch():
            return api.request("GET", "/api/admin/profiles"), api.request("GET", f"/api/admin/users/{uid}/shared-profiles")

        tasks.run(fetch, lambda r: self._profiles_dialog(user, *r),
                  lambda e: QMessageBox.warning(self, "Profiles", _message(e)), owner=self)

    def _profiles_dialog(self, user: dict, profiles: list[dict], shared) -> None:
        shared_ids = {p.get("id") if isinstance(p, dict) else p for p in (shared or [])}
        dlg, lay = _dialog(self, f"Profiles for {user.get('email', '')}")
        if user.get("role") == "admin":
            lay.addWidget(label("Admins work on every Profile already. This list matters once they are a Bidder "
                                "or Caller.", "Muted", wrap=True))
        lay.addWidget(label("Tick the Profiles this user works on.", "Muted", wrap=True))
        box = QListWidget()
        for p in profiles or []:
            item = QListWidgetItem(p.get("displayName") or "Profile")
            item.setData(Qt.UserRole, p.get("id"))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p.get("id") in shared_ids else Qt.Unchecked)
            box.addItem(item)
        lay.addWidget(box, 1)
        buttons = _ok_cancel(dlg, lay, "Save")

        def accept():
            ids = [box.item(i).data(Qt.UserRole) for i in range(box.count())
                   if box.item(i).checkState() == Qt.Checked]
            uid = user["id"]
            self._run(lambda: self.state.api.request("PUT", f"/api/admin/users/{uid}/shared-profiles",
                                                     json_body={"profileIds": ids}))
            dlg.accept()

        buttons.accepted.connect(accept)
        dlg.resize(460, 480)
        dlg.exec()

    def _history(self) -> None:
        user = self._current()
        if not user:
            return
        uid = user["id"]
        tasks.run(lambda: self.state.api.request("GET", f"/api/admin/users/{uid}/login-history"),
                  lambda rows: self._history_dialog(user, rows),
                  lambda e: QMessageBox.warning(self, "Sign-ins", _message(e)), owner=self)

    def _history_dialog(self, user: dict, rows: list[dict]) -> None:
        dlg, lay = _dialog(self, f"Sign-ins of {user.get('email', '')}", 820)
        table = _table(["When", "Where", "IP", "Browser", "System", "Network"])
        table.setRowCount(len(rows or []))
        for r, row in enumerate(rows or []):
            table.setItem(r, 0, _item(_when(row.get("createdAt"))))
            table.setItem(r, 1, _item(row.get("locationLabel") or "—"))
            table.setItem(r, 2, _item(row.get("ip") or "—"))
            table.setItem(r, 3, _item(row.get("browser") or "—"))
            table.setItem(r, 4, _item(" · ".join(x for x in (row.get("os"), row.get("deviceType")) if x) or "—"))
            table.setItem(r, 5, _item(row.get("isp") or row.get("org") or "—"))
        lay.addWidget(_boxed(table), 1)
        if not rows:
            lay.addWidget(label("No sign-ins yet.", "Muted"))
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dlg.reject)
        lay.addWidget(close)
        dlg.resize(860, 480)
        dlg.exec()


def _confirm_text(parent: QWidget, title: str, text: str) -> tuple[str, bool]:
    dlg, lay = _dialog(parent, title)
    lay.addWidget(label(text, "", wrap=True))
    edit = QLineEdit()
    lay.addWidget(edit)
    buttons = _ok_cancel(dlg, lay, "Delete")
    buttons.accepted.connect(dlg.accept)
    ok = dlg.exec() == QDialog.Accepted
    return edit.text(), ok


# ============================================================================ Tokens
class TokensPage(_Page):
    HEADERS = ["Profile", "Label", "Token", "Made by", "Made", "Last used", "Expires", "State"]

    def __init__(self, state: AppState):
        super().__init__(state, "Tokens", "Profile tokens for the app, the extension and the agent. One token opens "
                                          "one Profile. Only the Super Admin makes and revokes them.")
        self.rows: list[dict] = []
        self.new_btn = button("New token", "Primary", self._new)
        self.head.addWidget(self.new_btn, 0, Qt.AlignTop)
        self.table = _table(self.HEADERS)
        self.table.itemSelectionChanged.connect(self._selection)
        self.lay.addWidget(_boxed(self.table), 1)
        row = QHBoxLayout()
        self.revoke_btn = button("Revoke", "", self._revoke, "It stops working at once")
        row.addWidget(self.revoke_btn)
        row.addStretch(1)
        self.lay.addLayout(row)
        self._selection()
        if not state.session.is_super_admin:
            self.new_btn.setEnabled(False)
            self.set_error("Only the Super Admin can see, make and revoke tokens.")

    def reload(self) -> None:
        if not self.state.session.is_super_admin:
            return
        self.set_error("")
        tasks.run(lambda: self.state.api.request("GET", "/api/admin/tokens"), self._show, self.failed, owner=self)

    def _state(self, t: dict) -> tuple[str, str]:
        if t.get("revokedAt"):
            return "Revoked", "failed"
        exp = t.get("expiresAt")
        if exp:
            try:
                if datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now().astimezone():
                    return "Expired", "draft"
            except ValueError:
                pass
        return "Working", "offer"

    def _show(self, rows: list[dict]) -> None:
        self.rows = list(rows or [])
        t = self.table
        t.setRowCount(len(self.rows))
        for r, tok in enumerate(self.rows):
            text, kind = self._state(tok)
            t.setItem(r, 0, _item((tok.get("profile") or {}).get("name", ""), tok.get("id")))
            t.setItem(r, 1, _item(tok.get("label") or "—", muted=not tok.get("label")))
            t.setItem(r, 2, _item(f"{tok.get('prefix', 'rmv_')}…", muted=True))
            t.setItem(r, 3, _item(tok.get("createdBy") or "—", muted=True))
            t.setItem(r, 4, _item(_when(tok.get("createdAt"), False), muted=True))
            t.setItem(r, 5, _item(_when(tok.get("lastUsedAt")), muted=True))
            t.setItem(r, 6, _item(_when(tok.get("expiresAt"), False), muted=True))
            t.setItem(r, 7, _item(""))
            t.setCellWidget(r, 7, _chip_cell(text, kind))
        self._selection()

    def _current(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.selectionModel().hasSelection():
            return None
        tid = self.table.item(row, 0).data(Qt.UserRole)
        return next((t for t in self.rows if t.get("id") == tid), None)

    def _selection(self) -> None:
        tok = self._current()
        self.revoke_btn.setEnabled(bool(tok) and not tok.get("revokedAt"))

    def _new(self) -> None:
        tasks.run(lambda: self.state.api.request("GET", "/api/admin/profiles"), self._new_dialog,
                  lambda e: QMessageBox.warning(self, "Tokens", _message(e)), owner=self)

    def _new_dialog(self, profiles: list[dict]) -> None:
        dlg, lay = _dialog(self, "New token")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        profile = QComboBox()
        for p in profiles or []:
            profile.addItem(p.get("displayName") or "Profile", p.get("id"))
        index = profile.findData(self.state.profile_id)
        if index >= 0:
            profile.setCurrentIndex(index)
        form.addRow("Profile", profile)
        name = QLineEdit()
        name.setPlaceholderText("Who or what it is for (e.g. a bidder's name)")
        form.addRow("Label", name)
        days = QSpinBox()
        days.setRange(1, 365)
        days.setValue(90)
        days.setSuffix(" days")
        form.addRow("Works for", days)
        lay.addLayout(form)
        buttons = _ok_cancel(dlg, lay, "Make token")

        def accept():
            if not profile.currentData():
                return
            body = {"profileId": profile.currentData(), "label": name.text().strip(), "expiresInDays": days.value()}
            dlg.accept()
            tasks.run(lambda: self.state.api.request("POST", "/api/admin/tokens", json_body=body), self._made,
                      lambda e: QMessageBox.warning(self, "Tokens", _message(e)), owner=self)

        buttons.accepted.connect(accept)
        dlg.exec()

    def _made(self, result: dict) -> None:
        self.reload()
        token = (result or {}).get("token", "")
        dlg, lay = _dialog(self, "Token made", 560)
        lay.addWidget(label("Copy it now. It is shown only this once.", "Strong"))
        edit = QLineEdit(token)
        edit.setReadOnly(True)
        lay.addWidget(edit)
        row = QHBoxLayout()
        copied = label("", "Ok")

        def copy():
            QGuiApplication.clipboard().setText(token)
            copied.setText("✓ Copied")

        row.addWidget(button("Copy", "Primary", copy))
        row.addWidget(copied)
        row.addStretch(1)
        row.addWidget(button("Done", "", dlg.accept))
        lay.addLayout(row)
        dlg.exec()

    def _revoke(self) -> None:
        tok = self._current()
        if not tok:
            return
        who = (tok.get("profile") or {}).get("name", "")
        if QMessageBox.question(self, "Revoke token", f"Revoke this token for {who}? It stops working at once, in "
                                                      "the app, the extension and the agent.") != QMessageBox.Yes:
            return
        tid = tok["id"]
        tasks.run(lambda: self.state.api.request("DELETE", f"/api/admin/tokens/{tid}"), lambda _r: self.reload(),
                  lambda e: QMessageBox.warning(self, "Tokens", _message(e)), owner=self)


# ============================================================================ AI settings
class AiSettingsPage(_Page):
    def __init__(self, state: AppState):
        super().__init__(state, "AI settings", "The server's AI for resumes and cover letters: platform, model, key "
                                               "and the default prompts.")
        self.loaded: dict = {}
        self.saved = label("", "Ok")
        self.head.addWidget(self.saved, 0, Qt.AlignTop)
        self.save_btn = button("Save", "Primary", self._save)
        self.head.addWidget(self.save_btn, 0, Qt.AlignTop)

        card = Card("AI platform")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.provider = QComboBox()
        for key, text in AI_PROVIDERS:
            self.provider.addItem(text, key)
        form.addRow("Platform", self.provider)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(320)
        model_row.addWidget(self.model, 1)
        self.models_btn = button("Load models", "", self._load_models, "List the models the key can use")
        model_row.addWidget(self.models_btn)
        form.addRow("Model", model_row)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        form.addRow("API key", self.key)
        self.remove_key = QCheckBox("Remove the saved key (use the server's environment key)")
        form.addRow("", self.remove_key)
        self.key_note = label("", "Muted", wrap=True)
        form.addRow("", self.key_note)
        card.body.addLayout(form)
        self.lay.addWidget(card)

        prompts = QHBoxLayout()
        prompts.setSpacing(14)
        self.system_prompt = QPlainTextEdit()
        self.cover_prompt = QPlainTextEdit()
        for title, edit in (("Resume prompt", self.system_prompt), ("Cover letter prompt", self.cover_prompt)):
            box = Card(title)
            box.body.addWidget(edit, 1)
            box.body.addWidget(label("Empty = the built-in default. A Profile's own prompt wins over this.", "Muted",
                                     wrap=True))
            prompts.addWidget(box, 1)
        self.lay.addLayout(prompts, 1)
        self.provider.currentIndexChanged.connect(lambda _i: self.model.clear())

    def reload(self) -> None:
        self.set_error("")
        self.saved.setText("")
        tasks.run(lambda: self.state.api.request("GET", "/api/admin/ai"), self._show, self.failed, owner=self)

    def _show(self, data: dict) -> None:
        self.loaded = data or {}
        self.provider.blockSignals(True)
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.loaded.get("provider"))))
        self.provider.blockSignals(False)
        self.model.clear()
        self.model.setEditText(self.loaded.get("model") or "")
        self.system_prompt.setPlainText(self.loaded.get("systemPrompt") or "")
        self.cover_prompt.setPlainText(self.loaded.get("coverLetterPrompt") or "")
        self.key.clear()
        self.remove_key.setChecked(False)
        source = self.loaded.get("keySource")
        defaults = self.loaded.get("defaults") or {}
        self.key.setPlaceholderText("A key is saved — type to replace it" if source == "database"
                                    else "Paste the platform's API key")
        self.key_note.setText({
            "database": "Using the key saved here.",
            "environment": f"Using the server's {defaults.get('keyVariable', 'environment')} key.",
        }.get(source, "No key yet: the server can't make resumes itself. The app's Resume Maker still works "
                      "through ChatGPT, Claude or Gemini in Chrome."))
        self.remove_key.setVisible(source == "database")
        stamp = self.loaded.get("updatedAt")
        self.saved.setText(f"Last saved {_when(stamp)}" if stamp else "")

    def _load_models(self) -> None:
        body = {"provider": self.provider.currentData()}
        if self.key.text().strip():
            body["apiKey"] = self.key.text().strip()
        self.models_btn.setEnabled(False)

        def done(result: dict):
            self.models_btn.setEnabled(True)
            keep = self.model.currentText()
            self.model.clear()
            for m in (result or {}).get("models", []):
                self.model.addItem(m.get("displayName") or m.get("id"), m.get("id"))
            index = self.model.findData(keep)
            if index >= 0:
                self.model.setCurrentIndex(index)
            else:
                self.model.setEditText(keep or (result or {}).get("defaultModel", ""))

        def failed(error):
            self.models_btn.setEnabled(True)
            QMessageBox.warning(self, "Models", _message(error))

        tasks.run(lambda: self.state.api.request("POST", "/api/resume/models", json_body=body), done, failed,
                  owner=self)

    def _model_text(self) -> str:
        data = self.model.currentData()
        text = self.model.currentText().strip()
        return data if data and self.model.itemText(self.model.currentIndex()) == text else text

    def _save(self) -> None:
        old = self.loaded
        body: dict = {}
        if self.provider.currentData() != old.get("provider"):
            body["provider"] = self.provider.currentData()
        model = self._model_text()
        if model != (old.get("model") or ""):
            body["model"] = model or None
        for key, edit in (("systemPrompt", self.system_prompt), ("coverLetterPrompt", self.cover_prompt)):
            text = edit.toPlainText()
            if text.strip() != (old.get(key) or "").strip():
                body[key] = text if text.strip() else None
        if self.key.text().strip():
            body["apiKey"] = self.key.text().strip()
        elif self.remove_key.isChecked():
            body["apiKey"] = None
        if not body:
            self.saved.setText("Nothing changed")
            return
        self.save_btn.setEnabled(False)
        self.saved.setText("Saving…")

        def done(data):
            self.save_btn.setEnabled(True)
            self._show(data)
            self.saved.setText("✓ Saved")

        def failed(error):
            self.save_btn.setEnabled(True)
            self.saved.setText("")
            self.failed(error)

        tasks.run(lambda: self.state.api.request("PUT", "/api/admin/ai", json_body=body), done, failed, owner=self)


# ============================================================================ Pipeline
PIPELINE_COLUMNS = [
    ("Applied", ["Applied"]),
    ("Interviewing", [s for s in STATUSES if KIND[s] == "interview"]),
    ("Offer", [s for s in STATUSES if KIND[s] == "offer"]),
    ("Rejected", [s for s in STATUSES if KIND[s] == "failed"]),
]


def _all_bids(api, profile: str | None, statuses: list[str], sort: str = "bidDate", limit: int = 1000) -> list[dict]:
    """Every bid with these statuses (page by page, up to `limit`)."""
    out: list[dict] = []
    page = 1
    while len(out) < limit:
        params = {"page": page, "pageSize": 100, "sort": sort, "statuses": ",".join(statuses)}
        if profile and api.session.mode == "account":
            params["profileId"] = profile
        data = api.request("GET", "/api/bids", params=params, profile_id=profile) or {}
        out.extend(data.get("items", []))
        if page >= int(data.get("totalPages", 1)):
            break
        page += 1
    return out


class PipelinePage(_Page):
    def __init__(self, state: AppState):
        super().__init__(state, "Pipeline", "Applications past Draft, by stage. Click a card to change its status.")
        self.bids: dict[str, dict] = {}
        board = QHBoxLayout()
        board.setSpacing(12)
        self.columns: dict[str, tuple[QLabel, QListWidget]] = {}
        for title, _statuses in PIPELINE_COLUMNS:
            card = Card()
            card.body.setSpacing(8)
            head = QHBoxLayout()
            head.addWidget(label(title, "Strong"))
            head.addStretch(1)
            count = label("0", "Muted")
            head.addWidget(count)
            card.body.addLayout(head)
            lst = QListWidget()
            lst.setSpacing(3)
            lst.setWordWrap(True)
            lst.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            lst.itemClicked.connect(self._clicked)
            card.body.addWidget(lst, 1)
            board.addWidget(card, 1)
            self.columns[title] = (count, lst)
        self.lay.addLayout(board, 1)
        state.profile_changed.connect(lambda _p: self.reload() if self._loaded_once else None)
        state.data_changed.connect(lambda: self.reload() if self.isVisible() else None)

    def reload(self) -> None:
        self.set_error("")
        api, profile = self.state.api, self.state.request_profile

        def fetch():
            return {title: _all_bids(api, profile, statuses, limit=300) for title, statuses in PIPELINE_COLUMNS}

        tasks.run(fetch, self._show, self.failed, owner=self)

    def _show(self, columns: dict[str, list[dict]]) -> None:
        self.bids = {}
        show_profile = not self.state.profile_id
        for title, (count, lst) in self.columns.items():
            rows = columns.get(title, [])
            count.setText(str(len(rows)))
            lst.clear()
            for bid in rows:
                self.bids[bid["id"]] = bid
                lines = [f"{bid.get('company', '')}", bid.get("role", "")]
                meta = [bid.get("status", "")]
                if show_profile and (bid.get("candidate") or {}).get("displayName"):
                    meta.append(bid["candidate"]["displayName"])
                interviews = bid.get("interviews") or []
                upcoming = [i for i in interviews if i.get("dateTime", "") >= datetime.now().strftime("%Y-%m-%dT%H:%M")]
                if upcoming:
                    meta.append("Next: " + _when(upcoming[0]["dateTime"]))
                elif bid.get("bidDate"):
                    meta.append(_when(bid["bidDate"], False))
                item = QListWidgetItem("\n".join([*lines, " · ".join(m for m in meta if m)]))
                item.setData(Qt.UserRole, bid["id"])
                item.setToolTip(f"{bid.get('company', '')} — {bid.get('role', '')}\n{bid.get('status', '')}")
                lst.addItem(item)

    def _clicked(self, item: QListWidgetItem) -> None:
        bid = self.bids.get(item.data(Qt.UserRole))
        if not bid:
            return
        lst = item.listWidget()
        menu = QMenu(self)
        if bid.get("url"):
            from .. import chrome

            menu.addAction("Open job", lambda: chrome.open_url(bid["url"]))
            menu.addSeparator()
        current = bid.get("status")
        for status in STATUSES:
            if status in GROUP_STARTS:
                menu.addSeparator()
            action = QAction(("✓  " if status == current else "     ") + status, menu)
            action.triggered.connect(lambda _=False, s=status: self._set_status(bid, s))
            menu.addAction(action)
        menu.exec(lst.viewport().mapToGlobal(lst.visualItemRect(item).bottomLeft()))

    def _set_status(self, bid: dict, status: str) -> None:
        if status == bid.get("status"):
            return
        api = self.state.api
        profile = (bid.get("candidate") or {}).get("id") if self.state.session.mode == "token" else None

        def done(_n):
            self.state.data_changed.emit()
            self.reload()

        tasks.run(lambda: api.set_status([bid["id"]], status, profile), done,
                  lambda e: QMessageBox.warning(self, "Could not change the status", _message(e)), owner=self)


# ============================================================================ Calendar
class CalendarPage(_Page):
    def __init__(self, state: AppState):
        super().__init__(state, "Calendar", "Interviews by day. Pick a day to see who is on it.")
        self.events: list[tuple[datetime, dict, dict]] = []
        row = QHBoxLayout()
        row.setSpacing(16)
        cal_card = Card()
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setMinimumSize(420, 340)
        self.calendar.selectionChanged.connect(self._day)
        cal_card.body.addWidget(self.calendar)
        today = button("Today", "", lambda: self.calendar.setSelectedDate(QDate.currentDate()))
        cal_card.body.addWidget(today, 0, Qt.AlignLeft)
        cal_card.body.addStretch(1)
        row.addWidget(cal_card)

        right = QVBoxLayout()
        right.setSpacing(12)
        day_card = Card()
        self.day_title = label("", "Strong")
        day_card.body.addWidget(self.day_title)
        self.day_list = QListWidget()
        self.day_list.setWordWrap(True)
        day_card.body.addWidget(self.day_list, 1)
        right.addWidget(day_card, 1)
        soon_card = Card("Coming up")
        self.soon_list = QListWidget()
        self.soon_list.setWordWrap(True)
        soon_card.body.addWidget(self.soon_list, 1)
        right.addWidget(soon_card, 1)
        row.addLayout(right, 1)
        self.lay.addLayout(row, 1)
        state.profile_changed.connect(lambda _p: self.reload() if self._loaded_once else None)

    def reload(self) -> None:
        self.set_error("")
        api, profile = self.state.api, self.state.request_profile
        statuses = INTERVIEW_STATUSES + [s for s in STATUSES if KIND[s] == "failed"]
        tasks.run(lambda: _all_bids(api, profile, statuses), self._show, self.failed, owner=self)

    def _show(self, bids: list[dict]) -> None:
        self.events = []
        for bid in bids:
            for round_ in bid.get("interviews") or []:
                try:
                    moment = datetime.fromisoformat(str(round_.get("dateTime", "")).replace("Z", ""))
                except ValueError:
                    continue
                self.events.append((moment, bid, round_))
        self.events.sort(key=lambda e: e[0])
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        mark = QTextCharFormat()
        mark.setFontWeight(700)
        mark.setForeground(QBrush(QColor(theme.colors()["accent"])))
        for moment, _b, _r in self.events:
            self.calendar.setDateTextFormat(QDate(moment.year, moment.month, moment.day), mark)
        now = datetime.now()
        self.soon_list.clear()
        for moment, bid, round_ in [e for e in self.events if e[0] >= now][:30]:
            self.soon_list.addItem(self._line(moment, bid, round_, with_day=True))
        if not self.soon_list.count():
            self.soon_list.addItem("No interviews coming up.")
        self._day()

    def _line(self, moment: datetime, bid: dict, round_: dict, with_day: bool = False) -> str:
        when = moment.strftime("%a %b %d · %H:%M" if with_day else "%H:%M")
        who = (bid.get("candidate") or {}).get("displayName", "")
        tail = f"  ·  {who}" if who and not self.state.profile_id else ""
        return f"{when}   {bid.get('company', '')} — {round_.get('stage', '')}\n{bid.get('role', '')}{tail}"

    def _day(self) -> None:
        picked = self.calendar.selectedDate()
        day = date(picked.year(), picked.month(), picked.day())
        self.day_title.setText(day.strftime("%A, %B %d"))
        self.day_list.clear()
        for moment, bid, round_ in self.events:
            if moment.date() == day:
                self.day_list.addItem(self._line(moment, bid, round_))
        if not self.day_list.count():
            self.day_list.addItem("No interviews this day.")
