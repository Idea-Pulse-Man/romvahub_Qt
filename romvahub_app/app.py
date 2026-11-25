"""Starting the app: one copy at a time, the saved sign-in, then the main window (or the sign-in window)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, ORG_NAME, tasks, theme, vault
from .api import Api, ApiError, Session, TokenProfile
from .config import config
from .maker import Maker
from .state import AppState
from .ui.main_window import MainWindow
from .ui.signin import SignInWindow
from .ui.widgets import app_icon


class Controller:
    def __init__(self, app: QApplication, minimized: bool):
        self.app = app
        self.minimized = minimized
        self.signin: SignInWindow | None = None
        self.window: MainWindow | None = None
        self.state: AppState | None = None
        self.maker: Maker | None = None
        self.api: Api | None = None

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if config.method == "token":
            api = self._token_api()
            if api.session.tokens:
                self.open_main(api)
                return
            self.show_signin()
            return
        if not vault.refresh_token(config.server_url):
            self.show_signin()
            return
        api = Api(Session(server=config.server_url, mode="account", keep_signed_in=True))

        def failed(error: Exception) -> None:
            if isinstance(error, ApiError) and error.is_offline:
                self.show_signin(f"Can't reach {config.server_url}. Check your internet, then sign in.")
            else:
                self.show_signin("Your sign-in has ended. Please sign in again.")

        tasks.run(api.resume_saved_sign_in, lambda _u: self.open_main(api), failed)

    def _token_api(self) -> Api:
        session = Session(server=config.server_url, mode="token")
        for entry in config.token_entries(config.server_url):
            tp = TokenProfile.from_entry(entry)
            token = vault.profile_token(config.server_url, tp.profile_id)
            if token:
                session.tokens[tp.profile_id] = token
                session.token_profiles[tp.profile_id] = tp
        return Api(session)

    # ------------------------------------------------------------------ windows
    def show_signin(self, message: str = "") -> None:
        self.signin = SignInWindow(message)
        self.signin.connected.connect(self._connected)
        # Closing the sign-in window (✕) without connecting quits the app.
        self.signin.cancelled.connect(self.app.quit)
        self.signin.show()

    def _connected(self, api: Api) -> None:
        self.minimized = False
        # The main window first: the app must never be left with no window open.
        self.open_main(api)
        if self.signin:
            signin, self.signin = self.signin, None
            signin.close()
            signin.deleteLater()

    def open_main(self, api: Api) -> None:
        self.api = api
        self.state = AppState(api)
        self.maker = Maker(lambda: self.api)
        self.window = MainWindow(self.state, self.maker)
        self.window.sign_out.connect(self.sign_out)
        self.window.switch_method.connect(self.switch_method)
        self.window.theme_changed.connect(self.set_theme)
        self.state.signed_out.connect(self._ended)
        self.state.load_profiles()
        if config.maker_autostart:
            def autostart():
                if self.maker and self.state:
                    profile = self.state.request_profile if api.session.mode == "token" else None
                    self.maker.start(profile)
            QTimer.singleShot(3000, autostart)
        if self.minimized:
            self.minimized = False
        else:
            self.window.show()
        if api.session.mode == "token":
            self._recheck_tokens(api)

    def _recheck_tokens(self, api: Api) -> None:
        """Tokens deleted by the admin since last time show as "Revoked by admin"."""
        def check():
            changed = False
            for pid, token in list(api.session.tokens.items()):
                try:
                    api.check_token(token)
                    revoked = False
                except ApiError as error:
                    if error.is_offline:
                        continue
                    revoked = error.status == 401
                tp = api.session.token_profiles.get(pid)
                if tp and tp.revoked != revoked:
                    tp.revoked = revoked
                    changed = True
            return changed

        def done(changed: bool) -> None:
            if changed and self.state:
                config.set_token_entries(api.session.server, [p.to_entry() for p in api.session.token_profiles.values()])
                self.state.load_profiles()

        tasks.run(check, done, lambda _e: None)

    def _close_main(self) -> None:
        if self.window:
            self.window.shutdown()
            self.window.deleteLater()
            self.window = None
        self.state = None
        self.maker = None

    # ------------------------------------------------------------------ sign out
    def sign_out(self) -> None:
        api = self.api
        self._close_main()
        if api:
            if api.session.mode == "token":
                for pid in list(api.session.tokens):
                    vault.forget_profile_token(api.session.server, pid)
                config.set_token_entries(api.session.server, [])
            tasks.run(api.logout, lambda _r: None, lambda _e: None)
        self.api = None
        self.show_signin()

    def switch_method(self, method: str) -> None:
        api = self.api
        self._close_main()
        if api and api.session.mode == "account":
            tasks.run(api.logout, lambda _r: None, lambda _e: None)
        config.method = method
        self.api = None
        self.show_signin()

    def _ended(self, reason: str) -> None:
        self._close_main()
        self.api = None
        self.show_signin(f"Your sign-in ended: {reason}")

    def set_theme(self, choice: str) -> None:
        theme.apply(self.app, choice)
        if self.window:
            self.window.restyle()
            self.window.applications._render()
        if self.state:
            self.state.data_changed.emit()

    def show_existing(self) -> None:
        if self.window:
            self.window.show_normal()
        elif self.signin:
            self.signin.showNormal()
            self.signin.raise_()
            self.signin.activateWindow()


def _start_debug_log() -> None:
    """--debug: every server call, every error and the Resume Maker's log, on the console and in a file."""
    import logging
    import traceback

    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    from .config import data_dir

    path = data_dir() / "debug.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # The built RomvaHub.exe has no console (sys.stdout is None): the file only.
    handlers = [logging.FileHandler(path, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(fmt)
        root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("keyring").setLevel(logging.INFO)
    logging.getLogger("win32ctypes").setLevel(logging.INFO)
    log = logging.getLogger("romvahub")

    def excepthook(kind, value, tb):
        log.error("UNCAUGHT ERROR:\n%s", "".join(traceback.format_exception(kind, value, tb)))
        try:
            QMessageBox.critical(None, f"{APP_NAME} (debug)", f"{kind.__name__}: {value}\n\nDetails: {path}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = excepthook
    qt_levels = {QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
                 QtMsgType.QtFatalMsg: logging.CRITICAL}
    qInstallMessageHandler(lambda kind, _ctx, msg: logging.getLogger("qt").log(qt_levels.get(kind, logging.DEBUG), msg))
    log.info("romva hub debug mode. Server: %s. Log file: %s", config.server_url, path)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app, config.theme)

    # One copy at a time: a second start just brings the first one forward.
    socket = QLocalSocket()
    socket.connectToServer(APP_ID)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(APP_ID)
    server.listen(APP_ID)

    if "--debug" in sys.argv:
        _start_debug_log()
    controller = Controller(app, minimized="--minimized" in sys.argv)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), controller.show_existing()))
    try:
        controller.start()
    except Exception as error:  # noqa: BLE001 - last resort, shown to the user
        QMessageBox.critical(None, APP_NAME, f"romva hub could not start:\n{error}")
        return 1
    # Quitting is explicit: tray → Quit, or ✕ on the sign-in window. Windows that
    # close while switching (sign-in ↔ main window) never end the app.
    return app.exec()
