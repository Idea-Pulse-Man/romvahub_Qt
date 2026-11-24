"""The main window: menu on the left, the page, and the Resume Maker status at the bottom; plus the tray icon."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton, QStackedWidget,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .. import APP_VERSION, chrome
from ..config import config
from ..maker import Maker
from ..state import ALL, AppState
from .applications import ApplicationsPage
from .home import HomePage
from .profiles import ProfilesPage
from .resume_maker import ResumeMakerPage
from .settings import SettingsPage
from .widgets import Banner, Dot, app_icon, button, label

ADMIN_LINKS = [("Users", "/users"), ("Tokens", "/tokens"), ("AI settings", "/ai-settings"), ("Pipeline", "/pipeline"),
               ("Calendar", "/calendar")]


class MainWindow(QMainWindow):
    sign_out = Signal()
    switch_method = Signal(str)
    theme_changed = Signal(str)

    def __init__(self, state: AppState, maker: Maker):
        super().__init__()
        self.state = state
        self.maker = maker
        self.setWindowTitle("romva hub")
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self._quitting = False
        self._told_tray = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._topbar())
        self.offline = Banner()
        main.addWidget(self.offline)
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        main.addWidget(self._statusbar())
        root.addLayout(main, 1)

        self.home = HomePage(state, maker)
        self.applications = ApplicationsPage(state, maker)
        self.maker_page = ResumeMakerPage(state, maker)
        self.profiles = ProfilesPage(state)
        self.settings = SettingsPage(state)
        self.pages = {"home": self.home, "applications": self.applications, "maker": self.maker_page,
                      "profiles": self.profiles, "settings": self.settings}
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.home.go_tab.connect(self._go_tab)
        self.home.go_maker.connect(lambda: self.go("maker"))
        self.applications.open_settings.connect(lambda: self.go("settings"))
        self.settings.sign_out.connect(self.sign_out.emit)
        self.settings.switch_method.connect(self.switch_method.emit)
        self.settings.theme_changed.connect(self.theme_changed.emit)

        state.profiles_changed.connect(self._fill_profile_menu)
        state.profile_changed.connect(lambda _p: self._show_profile())
        state.online_changed.connect(self._online)
        maker.state_changed.connect(lambda _r: self._show_maker())
        maker.job_changed.connect(lambda _j: self._show_maker())
        maker.made.connect(self._made)

        self._tray()
        self._show_maker()
        self.go("applications")

    # ------------------------------------------------------------------ chrome
    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 14)
        lay.setSpacing(4)
        brand = QHBoxLayout()
        mark = label("r", "BrandMark")
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignCenter)
        brand.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("romva hub", "Brand"))
        names.addWidget(label(self.state.session.role_label if self.state.session.mode == "account" else "Bidder · tokens", "Muted"))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(14)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in (("home", "⌂   Home"), ("applications", "☰   Applications"), ("maker", "✦   Resume Maker"),
                          ("profiles", "◉   Profiles"), ("settings", "⚙   Settings")):
            btn = button(text, "NavButton", lambda _=False, k=key: self.go(k))
            btn.setCheckable(True)
            self.nav.addButton(btn)
            self.nav_buttons[key] = btn
            lay.addWidget(btn)

        if self.state.session.is_admin:
            lay.addWidget(label("ADMIN", "NavSection"))
            for text, path in ADMIN_LINKS:
                lay.addWidget(button(f"↗   {text}", "NavButton",
                                     lambda _=False, p=path: chrome.open_url(self.state.session.server + p),
                                     "Opens in the website (admin pages move into the app later)"))

        lay.addStretch(1)
        conn = QFrame()
        conn.setObjectName("Card")
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(2)
        cl.addWidget(label("Connected to", "Muted"))
        row = QHBoxLayout()
        self.conn_dot = Dot("#22C55E")
        row.addWidget(self.conn_dot)
        row.addWidget(label(self.state.session.server.replace("https://", "").replace("http://", ""), ""), 1)
        cl.addLayout(row)
        cl.addWidget(label(f"Version {APP_VERSION}", "Muted"))
        lay.addWidget(conn)
        return side

    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 10, 20, 10)
        self.profile_btn = QPushButton()
        self.profile_btn.setCursor(Qt.PointingHandCursor)
        self.profile_menu = QMenu(self)
        self.profile_btn.setMenu(self.profile_menu)
        lay.addWidget(self.profile_btn)
        lay.addStretch(1)
        self.online = label("● Online", "Ok")
        lay.addWidget(self.online)
        who = self.state.session
        user_btn = QPushButton(f"{who.display_name}  ·  {who.role_label}" if who.mode == "account" else "Token mode")
        menu = QMenu(self)
        menu.addAction("Settings", lambda: self.go("settings"))
        menu.addSeparator()
        menu.addAction("Sign out" if who.mode == "account" else "Disconnect", self.sign_out.emit)
        user_btn.setMenu(menu)
        lay.addWidget(user_btn)
        return bar

    def _statusbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 6, 16, 6)
        self.maker_dot = Dot("#9AA3B2")
        lay.addWidget(self.maker_dot)
        self.maker_state = QLabel()
        self.maker_state.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.maker_state)
        self.maker_note = label("", "Muted")
        lay.addWidget(self.maker_note, 1)
        self.maker_btn = button("", "", self._toggle_maker)
        lay.addWidget(self.maker_btn)
        lay.addSpacing(16)
        self.today = label("", "Muted")
        lay.addWidget(self.today)
        return bar

    def _tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("romva hub")
        menu = QMenu()
        menu.addAction("Open romva hub", self.show_normal)
        self.tray_maker = QAction("Start Resume Maker", menu)
        self.tray_maker.triggered.connect(self._toggle_maker)
        menu.addAction(self.tray_maker)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    # ------------------------------------------------------------------ behaviour
    def go(self, key: str) -> None:
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.nav_buttons[key].setChecked(True)

    def _go_tab(self, tab: str) -> None:
        self.go("applications")
        self.applications.set_tab(tab)

    def _fill_profile_menu(self) -> None:
        menu = self.profile_menu
        menu.clear()
        if self.state.can_pick_all:
            menu.addAction(("✓  " if not self.state.profile_id else "     ") + "All Profiles",
                           lambda: self.state.set_profile(ALL))
            menu.addSeparator()
        for p in self.state.profiles:
            text = ("✓  " if p["id"] == self.state.profile_id else "     ") + p["name"]
            if p.get("revoked"):
                text += "   (revoked by admin · locked)"
            action = menu.addAction(text, lambda pid=p["id"]: self.state.set_profile(pid))
            action.setEnabled(not p.get("revoked"))
        if self.state.session.mode == "token":
            menu.addSeparator()
            menu.addAction("+ Add or remove tokens", lambda: self.go("settings"))
        self._show_profile()

    def _show_profile(self) -> None:
        self.profile_btn.setText(f"Profile:  {self.state.profile_name}   ")
        if self.profile_menu.actions():
            self._refresh_checks()

    def _refresh_checks(self) -> None:
        for action in self.profile_menu.actions():
            text = action.text()
            if text.startswith("✓  ") or text.startswith("     "):
                name = text[3:] if text.startswith("✓  ") else text[5:]
                base = name.split("   (revoked")[0]
                mark = base == self.state.profile_name
                action.setText(("✓  " if mark else "     ") + name)

    def _online(self, online: bool) -> None:
        self.online.setText("● Online" if online else "● Offline")
        self.online.setObjectName("Ok" if online else "Error")
        self.online.style().unpolish(self.online)
        self.online.style().polish(self.online)
        self.conn_dot.set_color("#22C55E" if online else "#DC2626")
        self.offline.show_text("" if online else "Can't reach the server. Reconnecting… Nothing you did is lost.")

    def _show_maker(self) -> None:
        running = self.maker.running
        self.maker_dot.set_color("#22C55E" if running else "#9AA3B2")
        self.maker_state.setText("Resume Maker is running" if running else "Resume Maker is stopped")
        job = self.maker.job
        if running:
            self.maker_note.setText(f"Making #{job.number} {job.company} — {job.role} · {self.maker.ai_name()}" if job
                                    else f"Waiting for the next Draft · {self.maker.ai_name()}")
        else:
            self.maker_note.setText("Start it to make resumes for your Drafts.")
        self.maker_btn.setText("■ Stop" if running else "▶ Start")
        self.maker_btn.setObjectName("" if running else "Primary")
        self.maker_btn.style().unpolish(self.maker_btn)
        self.maker_btn.style().polish(self.maker_btn)
        self.tray_maker.setText("Stop Resume Maker" if running else "Start Resume Maker")
        self.today.setText(f"Made this session: {self.maker.made_today}")

    def _toggle_maker(self) -> None:
        if self.maker.running:
            self.maker.stop()
        else:
            profile = self.state.request_profile if self.state.session.mode == "token" else None
            self.maker.start(profile)
            if self.maker.readiness():
                self.go("maker")

    def _made(self, company: str) -> None:
        if config.notify_ready and self.tray.isVisible():
            self.tray.showMessage("Resume ready", f"{company}: the resume and cover letter are made.", app_icon(), 5000)

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self) -> None:
        self._quitting = True
        self.maker.stop()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            self.maker.stop()
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._told_tray:
            self._told_tray = True
            self.tray.showMessage("romva hub is still running",
                                  "It keeps working in the tray. Right-click the icon to quit.", app_icon(), 4000)

    def shutdown(self) -> None:
        """Close for good (sign out / switch method): no tray, nothing running."""
        self._quitting = True
        self.maker.stop()
        self.tray.hide()
        self.close()
