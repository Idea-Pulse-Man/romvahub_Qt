"""The main window: menu on the left, the page, and the Resume Maker status at the bottom; plus the tray icon."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .. import APP_VERSION, theme
from ..config import config
from ..maker import Maker
from ..state import ALL, AppState
from .admin import AiSettingsPage, CalendarPage, PipelinePage, TokensPage, UsersPage
from .applications import ApplicationsPage
from .home import HomePage
from .profiles import ProfilesPage
from .resume_maker import ResumeMakerPage
from .settings import SettingsPage
from .icons import icon, pixmap
from .widgets import Banner, Dot, app_icon, brand_mark, button, icon_button, label

# Admin pages, all inside the app: (key, menu text, icon, page class).
ADMIN_PAGES = [("users", "Users", "users", UsersPage), ("tokens", "Tokens", "key", TokensPage),
               ("ai", "AI settings", "sparkles", AiSettingsPage), ("pipeline", "Pipeline", "kanban", PipelinePage),
               ("calendar", "Calendar", "calendar", CalendarPage)]


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
        self.stack.setObjectName("MainStack")
        main.addWidget(self.stack, 1)
        main.addWidget(self._statusbar())
        root.addLayout(main, 1)

        from . import resume_actions

        resume_actions.MAKER = maker
        self.home = HomePage(state, maker)
        self.applications = ApplicationsPage(state, maker)
        self.maker_page = ResumeMakerPage(state, maker)
        self.profiles = ProfilesPage(state)
        self.settings = SettingsPage(state)
        self.pages = {"home": self.home, "applications": self.applications, "maker": self.maker_page,
                      "profiles": self.profiles, "settings": self.settings}
        if self.state.session.is_admin:
            for key, _text, _icon, page_class in ADMIN_PAGES:
                self.pages[key] = page_class(state)
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
        self.restyle()
        self.go("applications")

    # ------------------------------------------------------------------ chrome
    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 14)
        lay.setSpacing(3)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(brand_mark(36))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("romva hub", "Brand"))
        role = self.state.session.role_label if self.state.session.mode == "account" else "User · tokens"
        names.addWidget(label(role, "Faint"))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(16)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_icons: dict[str, str] = {}
        for key, text, icon_name in (("home", "Home", "home"), ("applications", "Applications", "list"),
                                     ("maker", "Resume Maker", "sparkles"), ("profiles", "Profiles", "user"),
                                     ("settings", "Settings", "sliders")):
            btn = button(f"  {text}", "NavButton", lambda _=False, k=key: self.go(k))
            btn.setCheckable(True)
            btn.setIconSize(QSize(18, 18))
            btn.toggled.connect(lambda _on: self._paint_nav())
            self.nav.addButton(btn)
            self.nav_buttons[key] = btn
            self.nav_icons[key] = icon_name
            lay.addWidget(btn)

        if self.state.session.is_admin:
            lay.addWidget(label("ADMIN", "NavSection"))
            for key, text, icon_name, _page in ADMIN_PAGES:
                btn = button(f"  {text}", "NavButton", lambda _=False, k=key: self.go(k))
                btn.setCheckable(True)
                btn.setIconSize(QSize(18, 18))
                btn.toggled.connect(lambda _on: self._paint_nav())
                self.nav.addButton(btn)
                self.nav_buttons[key] = btn
                self.nav_icons[key] = icon_name
                lay.addWidget(btn)

        lay.addStretch(1)
        conn = QFrame()
        conn.setObjectName("ConnCard")
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(3)
        cl.addWidget(label("Connected to", "Faint"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.conn_dot = Dot("#22C55E", 8)
        row.addWidget(self.conn_dot)
        row.addWidget(label(self.state.session.server.replace("https://", "").replace("http://", ""), "Strong"), 1)
        cl.addLayout(row)
        cl.addWidget(label(f"Version {APP_VERSION}", "Faint"))
        lay.addWidget(conn)
        return side

    def _paint_nav(self) -> None:
        c = theme.colors()
        for key, btn in self.nav_buttons.items():
            btn.setIcon(icon(self.nav_icons[key], c["accent"] if btn.isChecked() else c["text"], 18))

    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(12)

        self.profile_btn = QPushButton()
        self.profile_btn.setCursor(Qt.PointingHandCursor)
        self.profile_btn.setMinimumHeight(40)
        self.profile_btn.setToolTip("Choose the Profile")
        pl = QHBoxLayout(self.profile_btn)
        pl.setContentsMargins(14, 0, 10, 0)
        pl.setSpacing(8)
        self.profile_caption = label("Profile", "Faint")
        self.profile_name = label("", "Strong")
        self.profile_chevron = QLabel()
        for widget in (self.profile_caption, self.profile_name, self.profile_chevron):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
            pl.addWidget(widget)
        self.profile_menu = QMenu(self)
        self.profile_btn.setMenu(self.profile_menu)
        lay.addWidget(self.profile_btn)

        search_box = QWidget()
        sl = QHBoxLayout(search_box)
        sl.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setObjectName("TopSearch")
        self.search.setPlaceholderText("Search company or role")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(40)
        self.search.textChanged.connect(self._search)
        sl.addWidget(self.search)
        self.search_icon = QLabel(self.search)
        self.search_icon.move(12, 12)
        self.search_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(search_box, 1)

        self.online = QLabel("●  Online")
        self.online.setObjectName("OnlinePill")
        lay.addWidget(self.online)
        self.theme_btn = icon_button("moon", "Switch to dark theme", self._toggle_theme)
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setFixedSize(38, 38)
        lay.addWidget(self.theme_btn)

        who = self.state.session
        name = who.display_name if who.mode == "account" else "Token mode"
        self.user_btn = QPushButton()
        self.user_btn.setCursor(Qt.PointingHandCursor)
        self.user_btn.setMinimumHeight(40)
        ul = QHBoxLayout(self.user_btn)
        ul.setContentsMargins(8, 0, 10, 0)
        ul.setSpacing(8)
        avatar = QLabel("".join(part[:1] for part in name.replace(".", " ").split()[:2]).upper() or "R")
        avatar.setObjectName("Avatar")
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignCenter)
        user_name = label(name, "Strong")
        self.user_chevron = QLabel()
        for widget in (avatar, user_name, self.user_chevron):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
            ul.addWidget(widget)
        self.user_btn.setMinimumWidth(QFontMetrics(self.user_btn.font()).horizontalAdvance(name) + 90)
        menu = QMenu(self)
        menu.addAction(f"{who.role_label}" if who.mode == "account" else "Connected with tokens").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Settings", lambda: self.go("settings"))
        menu.addAction("Sign out" if who.mode == "account" else "Disconnect", self.sign_out.emit)
        self.user_btn.setMenu(menu)
        lay.addWidget(self.user_btn)
        return bar

    def _search(self, text: str) -> None:
        if self.stack.currentWidget() is not self.applications:
            self.go("applications")
        self.applications.set_search(text)

    def _toggle_theme(self) -> None:
        current = theme.colors()["name"]
        choice = "light" if current == "dark" else "dark"
        config.theme = choice
        self.theme_changed.emit(choice)

    def restyle(self) -> None:
        """Icons and colours that are not in the style sheet (after a theme change)."""
        c = theme.colors()
        dark = c["name"] == "dark"
        self.theme_btn.setIcon(icon("sun" if dark else "moon", c["text"], 18))
        self.theme_btn.setToolTip("Switch to light theme" if dark else "Switch to dark theme")
        self.search_icon.setPixmap(pixmap("search", c["faint"], 16, 2.0))
        self.user_chevron.setPixmap(pixmap("chevron", c["muted"], 14, 2.2))
        self.profile_chevron.setPixmap(pixmap("chevron", c["muted"], 14, 2.2))
        self._paint_nav()
        self._online(self.state.online)
        self._show_maker()

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
        name = self.state.profile_name
        self.profile_name.setText(name)
        fm = QFontMetrics(self.profile_name.font())
        self.profile_btn.setFixedWidth(fm.horizontalAdvance(name) + fm.horizontalAdvance("Profile") + 74)
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
        self.online.setText("●  Online" if online else "●  Offline")
        self.online.setObjectName("OnlinePill" if online else "OfflinePill")
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
        self.maker_btn.setText("Stop" if running else "Start")
        self.maker_btn.setObjectName("" if running else "Primary")
        c = theme.colors()
        self.maker_btn.setIcon(icon("stop" if running else "play", c["text"] if running else c["accent_fg"], 12))
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
