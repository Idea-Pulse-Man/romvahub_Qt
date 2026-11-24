"""The first window: connect with email and password, or with Profile tokens."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout,
    QWidget,
)

from .. import APP_VERSION, tasks, vault
from ..api import Api, ApiError, MfaRequired, Session, TokenProfile, mask_token
from ..config import config
from .widgets import Card, Segmented, app_icon, button, label


class SignInWindow(QWidget):
    """Emits `connected(api)` once signed in (account) or once tokens are added (token mode)."""

    connected = Signal(object)
    cancelled = Signal()  # closed with ✕ before connecting

    def __init__(self, message: str = ""):
        super().__init__()
        self._finished = False
        self.setWindowTitle("romva hub — Connect")
        self.setWindowIcon(app_icon())
        self.setObjectName("Page")
        self.resize(560, 720)
        self._challenge: dict | None = None
        self._pending_tokens: dict[str, tuple[str, dict]] = {}  # profileId -> (token, info)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        card = Card()
        card.setMaximumWidth(480)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        card.body.setContentsMargins(32, 30, 32, 26)
        card.body.setSpacing(14)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        mark = label("r", "BrandMark")
        mark.setFixedSize(52, 52)
        mark.setAlignment(Qt.AlignCenter)
        mark_row = QHBoxLayout()
        mark_row.addStretch(1)
        mark_row.addWidget(mark)
        mark_row.addStretch(1)
        card.body.addLayout(mark_row)
        title = label("Connect to romva hub", "Title")
        title.setAlignment(Qt.AlignCenter)
        card.body.addWidget(title)
        sub = label("Choose how you connect. You can change this later in Settings.", "Subtitle", wrap=True)
        sub.setAlignment(Qt.AlignCenter)
        card.body.addWidget(sub)

        self.method = Segmented([("account", "Email and password"), ("token", "Tokens")], config.method)
        self.method.changed.connect(self._switch)
        seg_row = QHBoxLayout()
        seg_row.addStretch(1)
        seg_row.addWidget(self.method)
        seg_row.addStretch(1)
        card.body.addLayout(seg_row)

        # The three forms; only the one in use is shown (hidden ones take no space).
        self.forms = [self._account_page(), self._mfa_page(), self._token_page()]
        for form in self.forms:
            card.body.addWidget(form)

        self.error = label(message, "Error", wrap=True)
        self.error.setVisible(bool(message))
        card.body.addWidget(self.error)

        foot = QHBoxLayout()
        self.server_label = label("", "Muted")
        foot.addWidget(self.server_label)
        foot.addStretch(1)
        foot.addWidget(button("Change server", "Link", self._change_server))
        foot.addWidget(label(f"v{APP_VERSION}", "Muted"))
        card.body.addLayout(foot)
        self._show_server()
        self._switch(config.method)
        self._load_saved_tokens()

    # ------------------------------------------------------------------ pages
    def _account_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("EMAIL", "Label"))
        self.email = QLineEdit(config.last_email)
        self.email.setPlaceholderText("you@example.com")
        lay.addWidget(self.email)
        lay.addSpacing(6)
        lay.addWidget(label("PASSWORD", "Label"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Your password")
        self.password.returnPressed.connect(self._sign_in)
        lay.addWidget(self.password)
        self.keep = QCheckBox("Keep me signed in on this computer")
        self.keep.setChecked(config.keep_signed_in)
        lay.addWidget(self.keep)
        lay.addWidget(label("You get every Profile your admin assigned to your account.", "Muted", wrap=True))
        self.sign_in_btn = button("Sign in", "Primary", self._sign_in)
        self.sign_in_btn.setMinimumHeight(40)
        lay.addWidget(self.sign_in_btn)
        return page

    def _mfa_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("Authenticator code", "Label"))
        lay.addWidget(label("Enter the 6-digit code from your authenticator app.", "Muted", wrap=True))
        self.code = QLineEdit()
        self.code.setMaxLength(6)
        self.code.setPlaceholderText("123456")
        self.code.returnPressed.connect(self._verify)
        lay.addWidget(self.code)
        self.verify_btn = button("Verify", "Primary", self._verify)
        self.verify_btn.setMinimumHeight(40)
        lay.addWidget(self.verify_btn)
        lay.addWidget(button("Back", "Link", lambda: self._show_page(0)))
        return page

    def _token_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("Add a Profile token", "Label"))
        row = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("rmv_…  (paste the token your admin gave you)")
        self.token_input.returnPressed.connect(self._add_token)
        row.addWidget(self.token_input, 1)
        self.add_btn = button("Add", "", self._add_token)
        row.addWidget(self.add_btn)
        lay.addLayout(row)
        lay.addWidget(label("One token opens one Profile. Add a token for each Profile you work on.", "Muted", wrap=True))
        self.token_list = QListWidget()
        self.token_list.setMinimumHeight(120)
        lay.addWidget(self.token_list)
        self.remove_btn = button("Remove selected", "Link", self._remove_token)
        lay.addWidget(self.remove_btn)
        self.connect_btn = button("Add a token first", "Primary", self._connect_tokens)
        self.connect_btn.setMinimumHeight(40)
        lay.addWidget(self.connect_btn)
        return page

    # ------------------------------------------------------------------ helpers
    def _finish(self) -> None:
        self._finished = True

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._finished:
            self.cancelled.emit()
        super().closeEvent(event)

    def _show_server(self) -> None:
        self.server_label.setText(f"Server: {config.server_url.replace('https://', '')}")

    def _change_server(self) -> None:
        text, ok = QInputDialog.getText(self, "Server", "romva server address:", text=config.server_url)
        if ok and text.strip():
            url = text.strip()
            if not url.startswith("http"):
                url = "https://" + url
            config.server_url = url
            self._show_server()
            self._pending_tokens.clear()
            self._load_saved_tokens()

    def _show_page(self, index: int) -> None:
        """Show one form; the card is only as tall as that form."""
        for i, form in enumerate(self.forms):
            form.setVisible(i == index)

    def _switch(self, method: str) -> None:
        config.method = method
        self.method.set_current(method)
        self._show_page(2 if method == "token" else 0)
        self._set_error("")

    def _set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def _busy(self, btn, busy: bool, text: str) -> None:
        btn.setEnabled(not busy)
        btn.setText(text)

    def _new_api(self, mode: str) -> Api:
        return Api(Session(server=config.server_url, mode=mode, keep_signed_in=self.keep.isChecked()))

    # ------------------------------------------------------------------ account
    def _sign_in(self) -> None:
        email, password = self.email.text().strip(), self.password.text()
        if not email or not password:
            self._set_error("Enter your email and password.")
            return
        config.last_email = email
        config.keep_signed_in = self.keep.isChecked()
        self._api = self._new_api("account")
        self._busy(self.sign_in_btn, True, "Signing in…")
        self._set_error("")
        tasks.run(lambda: self._api.login(email, password), self._signed_in, self._sign_in_failed, owner=self)

    def _sign_in_failed(self, error: Exception) -> None:
        self._busy(self.sign_in_btn, False, "Sign in")
        if isinstance(error, MfaRequired):
            self._challenge = error.challenge
            self.code.clear()
            self._show_page(1)
            self.code.setFocus()
            return
        self._set_error(getattr(error, "message", str(error)))

    def _verify(self) -> None:
        code = self.code.text().strip()
        if not self._challenge or len(code) != 6:
            self._set_error("Enter the 6-digit code.")
            return
        self._busy(self.verify_btn, True, "Checking…")
        challenge_id = self._challenge.get("challengeId")
        tasks.run(lambda: self._api.verify_mfa(challenge_id, code), self._signed_in,
                  lambda e: (self._busy(self.verify_btn, False, "Verify"), self._set_error(getattr(e, "message", str(e)))),
                  owner=self)

    def _signed_in(self, _user) -> None:
        self._busy(self.sign_in_btn, False, "Sign in")
        self._busy(self.verify_btn, False, "Verify")
        self.password.clear()
        self._finish()
        self.connected.emit(self._api)

    # ------------------------------------------------------------------ tokens
    def _load_saved_tokens(self) -> None:
        self._pending_tokens.clear()
        for entry in config.token_entries(config.server_url):
            tp = TokenProfile.from_entry(entry)
            token = vault.profile_token(config.server_url, tp.profile_id)
            if token:
                self._pending_tokens[tp.profile_id] = (token, {"profile": {"id": tp.profile_id, "name": tp.profile_name},
                                                               "expiresAt": tp.expires_at, "label": tp.label})
        self._refresh_token_list()

    def _add_token(self) -> None:
        token = self.token_input.text().strip()
        if not token.startswith("rmv_"):
            self._set_error("A Profile token starts with rmv_.")
            return
        checker = self._new_api("token")
        self._busy(self.add_btn, True, "Checking…")
        self._set_error("")

        def done(info: dict) -> None:
            self._busy(self.add_btn, False, "Add")
            pid = str((info.get("profile") or {}).get("id"))
            self._pending_tokens[pid] = (token, info)
            self.token_input.clear()
            self._refresh_token_list()

        def failed(error: Exception) -> None:
            self._busy(self.add_btn, False, "Add")
            message = getattr(error, "message", str(error))
            if isinstance(error, ApiError) and error.status == 401:
                message = "This token was refused: it was deleted, has expired, or was typed wrong."
            self._set_error(message)

        tasks.run(lambda: checker.check_token(token), done, failed, owner=self)

    def _remove_token(self) -> None:
        item = self.token_list.currentItem()
        if item:
            self._pending_tokens.pop(item.data(Qt.UserRole), None)
            self._refresh_token_list()

    def _refresh_token_list(self) -> None:
        self.token_list.clear()
        for pid, (token, info) in self._pending_tokens.items():
            expires = (info.get("expiresAt") or "")[:10] or "never"
            item = QListWidgetItem(f"✓  {(info.get('profile') or {}).get('name', 'Profile')}    {mask_token(token)} · expires {expires}")
            item.setData(Qt.UserRole, pid)
            self.token_list.addItem(item)
        n = len(self._pending_tokens)
        self.connect_btn.setEnabled(n > 0)
        self.connect_btn.setText(f"Connect with {n} Profile{'s' if n != 1 else ''}" if n else "Add a token first")

    def _connect_tokens(self) -> None:
        api = self._new_api("token")
        # Saved fresh: what was removed here is forgotten too.
        for entry in config.token_entries(config.server_url):
            if entry.get("profileId") not in self._pending_tokens:
                vault.forget_profile_token(config.server_url, entry["profileId"])
        entries = []
        for pid, (token, info) in self._pending_tokens.items():
            tp = TokenProfile(profile_id=pid, profile_name=str((info.get("profile") or {}).get("name") or "Profile"),
                              mask=mask_token(token), label=str(info.get("label") or ""), expires_at=info.get("expiresAt"))
            api.session.tokens[pid] = token
            api.session.token_profiles[pid] = tp
            vault.save_profile_token(config.server_url, pid, token)
            entries.append(tp.to_entry())
        config.set_token_entries(config.server_url, entries)
        config.method = "token"
        self._finish()
        self.connected.emit(api)
