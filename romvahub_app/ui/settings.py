"""Settings: connection (account or tokens), rows per page, theme, Chrome and start-up."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import APP_VERSION, tasks
from ..api import Api, Session
from ..chrome import find_chrome
from ..config import PAGE_SIZES, config
from ..state import AppState
from .widgets import Card, Segmented, button, label, page_header


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    sign_out = Signal()
    switch_method = Signal(str)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.sizes.set_current(str(config.page_size))  # it can be changed under the Applications table too

    def __init__(self, state: AppState):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        inner.setObjectName("Page")
        scroll.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)
        head = QHBoxLayout()
        head.addWidget(page_header("Settings", "Changes are saved right away."), 1)
        self.saved = label("", "Ok")
        head.addWidget(self.saved)
        lay.addLayout(head)

        # Connection.
        conn = Card("Connection")
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("How this app connects to the server", ""))
        text.addWidget(label(f"Server: {state.session.server}  ·  Switching signs out of the current method first.", "Muted", wrap=True))
        row.addLayout(text, 1)
        self.method = Segmented([("account", "Email and password"), ("token", "Tokens")], state.session.mode)
        self.method.changed.connect(self._switch)
        row.addWidget(self.method)
        conn.body.addLayout(row)
        if state.session.mode == "account":
            who = state.session.user or {}
            line = QHBoxLayout()
            line.addWidget(label(f"Signed in as {who.get('email', '')}  ·  {state.session.role_label}", ""), 1)
            line.addWidget(button("Sign out", "", self.sign_out.emit))
            conn.body.addLayout(line)
        else:
            conn.body.addWidget(label("Your Profiles in this app. One token opens one Profile. Your admin makes tokens "
                                      "and can delete them at any time.", "Muted", wrap=True))
            add = QHBoxLayout()
            self.new_token = QLineEdit()
            self.new_token.setPlaceholderText("Paste a new token: rmv_…")
            self.new_token.returnPressed.connect(self._add_token)
            add.addWidget(self.new_token, 1)
            self.add_btn = button("+ Add token", "", self._add_token)
            add.addWidget(self.add_btn)
            conn.body.addLayout(add)
            self.token_error = label("", "Error", wrap=True)
            self.token_error.hide()
            conn.body.addWidget(self.token_error)
            self.tokens = QTableWidget(0, 5)
            self.tokens.setHorizontalHeaderLabels(["Profile", "Token", "Expires", "Status", ""])
            self.tokens.verticalHeader().hide()
            self.tokens.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.tokens.setMinimumHeight(170)
            self.tokens.verticalHeader().setDefaultSectionSize(42)
            self.tokens.setEditTriggers(QTableWidget.NoEditTriggers)
            conn.body.addWidget(self.tokens)
            line = QHBoxLayout()
            line.addStretch(1)
            line.addWidget(button("Disconnect all", "", self.sign_out.emit))
            conn.body.addLayout(line)
            self._fill_tokens()
        lay.addWidget(conn)

        # Applications list.
        apps = Card("Applications list")
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("Rows per page", ""))
        text.addWidget(label("How many applications show on one page. Also picked under the table. "
                             "Default is 5.", "Muted", wrap=True))
        row.addLayout(text, 1)
        self.sizes = Segmented([(str(n), str(n)) for n in PAGE_SIZES], str(config.page_size))
        self.sizes.changed.connect(lambda v: self._saved(setattr(config, "page_size", int(v))))
        row.addWidget(self.sizes)
        apps.body.addLayout(row)
        lay.addWidget(apps)

        # Appearance.
        look = Card("Appearance")
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("Theme", ""))
        text.addWidget(label("Light, dark, or follow your Windows setting.", "Muted"))
        row.addLayout(text, 1)
        theme = Segmented([("light", "Light"), ("dark", "Dark"), ("system", "Same as Windows")], config.theme)
        theme.changed.connect(self._theme)
        row.addWidget(theme)
        look.body.addLayout(row)
        lay.addWidget(look)

        # Start-up and Chrome.
        system = Card("This computer")
        self.run_at_login = QCheckBox("Start romva hub when Windows starts (in the tray)")
        self.run_at_login.setChecked(config.start_with_windows)
        self.run_at_login.toggled.connect(lambda on: self._saved(setattr(config, "start_with_windows", on)))
        system.body.addWidget(self.run_at_login)
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("Chrome location", ""))
        self.chrome_label = label(find_chrome() or "Not found", "Muted", wrap=True)
        text.addWidget(self.chrome_label)
        row.addLayout(text, 1)
        row.addWidget(button("Change…", "", self._choose_chrome))
        system.body.addLayout(row)
        system.body.addWidget(label("Apply opens jobs in this Chrome. The “Romva Apply (Alt+V)” extension must be "
                                    "installed there and signed in.", "Muted", wrap=True))
        lay.addWidget(system)

        # The app's own Chrome: where you bid, and where Resumes are made (browser.py).
        own = Card("The app's Chrome (bidding and Resumes)")
        own.body.addWidget(label("A Chrome of the app's own, with its own sign-ins, Romva Apply in it, and your proxy. "
                                 "Once Romva Apply is added there, Apply opens jobs in it.", "Muted", wrap=True))
        self.own_state = label("", "", wrap=True)
        own.body.addWidget(self.own_state)
        row = QHBoxLayout()
        row.addWidget(button("Open Chrome", "Primary", self._open_own_chrome))
        row.addWidget(button("Restart Chrome", "", self._restart_own_chrome, "A new Romva Apply or proxy takes effect"))
        row.addWidget(button("Add Romva Apply…", "", self._add_extension, "Once: Developer mode -> Load unpacked"))
        row.addStretch(1)
        own.body.addLayout(row)
        engine_row = QHBoxLayout()
        engine_row.addWidget(label("Resume Maker runs in", ""), 1)
        self.engine = Segmented([("agent", "This app (Resume agent)"), ("browser", "Chrome + Romva Apply")],
                                config.maker_engine)
        self.engine.changed.connect(lambda key: self._saved(setattr(config, "maker_engine", key)))
        engine_row.addWidget(self.engine)
        own.body.addLayout(engine_row)
        own.body.addWidget(label("Proxy (for example your SmartProxy gateway). Empty: no proxy.", "Label"))
        proxy = QHBoxLayout()
        self.proxy_host = QLineEdit(config.proxy_host)
        self.proxy_host.setPlaceholderText("Host, e.g. gate.smartproxy.com")
        self.proxy_port = QLineEdit(config.proxy_port)
        self.proxy_port.setPlaceholderText("Port")
        self.proxy_port.setMaximumWidth(90)
        self.proxy_user = QLineEdit(config.proxy_user)
        self.proxy_user.setPlaceholderText("Username")
        self.proxy_pass = QLineEdit(config.proxy_password)
        self.proxy_pass.setPlaceholderText("Password")
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        for field, stretch in ((self.proxy_host, 3), (self.proxy_port, 1), (self.proxy_user, 2), (self.proxy_pass, 2)):
            proxy.addWidget(field, stretch)
        own.body.addLayout(proxy)
        self.proxy_bypass = QLineEdit(config.proxy_bypass)
        self.proxy_bypass.setPlaceholderText("Sites that skip the proxy, separated by ; (none unless you add them)")
        own.body.addWidget(self.proxy_bypass)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(button("Save proxy", "", self._save_proxy, "Then Restart Chrome"))
        own.body.addLayout(save_row)
        lay.addWidget(own)
        self._show_own_chrome()

        about = Card("About")
        about.body.addWidget(label(f"romva hub {APP_VERSION}", ""))
        lay.addWidget(about)
        lay.addStretch(1)

    # ------------------------------------------------------------------ the app's Chrome
    def _show_own_chrome(self) -> None:
        from .. import browser

        installed = browser.extension_installed()
        self.own_state.setText(
            f"Romva Apply {browser.version_text()} in {browser.extension_dir()}  ·  "
            + ("added to the app's Chrome" if installed else "not added to the app's Chrome yet: click “Add Romva Apply…”")
            + f"  ·  this computer: {browser.worker_name()}")

    def _open_own_chrome(self) -> None:
        from .. import browser

        if not browser.open_urls(f"{config.server_url}/applications"):
            QMessageBox.warning(self, "Chrome", "Chrome was not found. Choose it under “This computer”.")
        self._show_own_chrome()

    def _restart_own_chrome(self) -> None:
        from .. import browser

        browser.sync_extension()
        if not browser.restart():
            QMessageBox.warning(self, "Chrome", "Chrome was not found. Choose it under “This computer”.")
        self._show_own_chrome()

    def _add_extension(self) -> None:
        from .. import browser

        browser.sync_extension()
        browser.write_configs()
        if not browser.open_urls("chrome://extensions/"):
            QMessageBox.warning(self, "Chrome", "Chrome was not found. Choose it under “This computer”.")
            return
        QMessageBox.information(self, "Add Romva Apply", browser.install_steps())
        self._show_own_chrome()

    def _save_proxy(self) -> None:
        from .. import browser

        config.proxy_host = self.proxy_host.text()
        config.proxy_port = self.proxy_port.text()
        config.proxy_user = self.proxy_user.text()
        config.proxy_password = self.proxy_pass.text()
        config.proxy_bypass = self.proxy_bypass.text()
        browser.write_configs()
        self._saved()
        if browser.is_running() and QMessageBox.question(
                self, "Proxy", "Restart the app's Chrome now, so the proxy takes effect?") == QMessageBox.Yes:
            browser.restart()

    # ------------------------------------------------------------------ actions
    def _saved(self, _=None) -> None:
        self.saved.setText("✓ Saved")

    def _theme(self, choice: str) -> None:
        config.theme = choice
        self._saved()
        self.theme_changed.emit(choice)

    def _switch(self, method: str) -> None:
        if method == self.state.session.mode:
            return
        answer = QMessageBox.question(
            self, "Switch connection method",
            "Switching signs you out of the current method. Continue?",
        )
        if answer == QMessageBox.Yes:
            self.switch_method.emit(method)
        else:
            self.method.set_current(self.state.session.mode)

    def _choose_chrome(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose chrome.exe", "", "Programs (*.exe)")
        if path:
            config.chrome_path = path
            self.chrome_label.setText(path)
            self._saved()

    # ------------------------------------------------------------------ tokens
    def _fill_tokens(self) -> None:
        profiles = list(self.state.session.token_profiles.values())
        self.tokens.setRowCount(len(profiles))
        for r, tp in enumerate(profiles):
            self.tokens.setItem(r, 0, QTableWidgetItem(tp.profile_name))
            self.tokens.setItem(r, 1, QTableWidgetItem(tp.mask))
            self.tokens.setItem(r, 2, QTableWidgetItem((tp.expires_at or "")[:10] or "never"))
            status = QTableWidgetItem("Revoked by admin" if tp.revoked else "● Working")
            status.setForeground(Qt.red if tp.revoked else Qt.darkGreen)
            self.tokens.setItem(r, 3, status)
            self.tokens.setCellWidget(r, 4, button("Remove", "", lambda _=False, pid=tp.profile_id: self._remove(pid)))

    def _remove(self, profile_id: str) -> None:
        self.state.remove_token(profile_id)
        self._fill_tokens()
        self.state.load_profiles()
        self._saved()

    def _add_token(self) -> None:
        token = self.new_token.text().strip()
        if not token.startswith("rmv_"):
            self._token_error("A Profile token starts with rmv_.")
            return
        checker = Api(Session(server=config.server_url, mode="token"))
        self.add_btn.setEnabled(False)

        def done(info: dict) -> None:
            self.add_btn.setEnabled(True)
            self.state.add_token(info, token)
            self.new_token.clear()
            self._token_error("")
            self._fill_tokens()
            self.state.load_profiles()
            self._saved()

        def failed(error: Exception) -> None:
            self.add_btn.setEnabled(True)
            message = getattr(error, "message", str(error))
            if getattr(error, "status", 0) == 401:
                message = "This token was refused: it was deleted, has expired, or was typed wrong."
            self._token_error(message)

        tasks.run(lambda: checker.check_token(token), done, failed, owner=self)

    def _token_error(self, text: str) -> None:
        self.token_error.setText(text)
        self.token_error.setVisible(bool(text))
