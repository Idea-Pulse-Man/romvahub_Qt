"""The main screen: every application of the Profile, with Apply, Open job, status and documents in each row."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import chrome, tasks, theme
from ..config import config
from ..statuses import GROUP_STARTS, STATUSES, TABS, display_status
from ..state import AppState
from .doc_viewer import DocViewer
from .icons import pixmap
from .widgets import Chip, CountTabs, Toast, button, icon_button, label, page_header, with_icon

COLUMNS = ["", "Company", "Role", "Location", "Found", "Status", "Resume", "Cover letter", "Actions"]
# Fixed columns (px) and how the rest of the width is shared by the text columns.
FIXED = {"": 44, "Found": 76, "Status": 168, "Resume": 104, "Cover letter": 116, "Actions": 142}
CENTERED = {"", "Found", "Status", "Resume", "Cover letter", "Actions"}
SHARE = {"Company": 1.0, "Profile": 0.75, "Role": 1.45, "Location": 1.0}
MINIMUM = {"Company": 120, "Profile": 90, "Role": 140, "Location": 100}


class ApplicationsPage(QWidget):
    open_settings = Signal()
    counts_changed = Signal(dict)

    def __init__(self, state: AppState, maker):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.maker = maker
        self.tab = "ready"
        # Opens on Ready; the first counts move it to Draft when nothing is Ready.
        self._auto_tab = True
        self.page = 1
        self.total = 0
        self.total_pages = 1
        self.rows: list[dict] = []
        self.checked: set[str] = set()
        self._version = ""
        self._undo = None
        self._load_seq = 0
        self._search_text = ""
        self._col: dict[str, int] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 14)
        lay.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(page_header("Applications", "Jobs your scraper found for this profile. Apply, open or download "
                                                  "right from each row."), 1)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(lambda: self.reload(reset_page=True))
        self.refresh_btn = icon_button("refresh", "Refresh", lambda: self.reload())
        head.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        self.add_btn = button("Add job", "", self._add_job, "Add a job by hand (opens the website form)")
        head.addWidget(self.add_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.tabs = CountTabs([(key, text) for key, text, _q in TABS], self.tab)
        self.tabs.changed.connect(self._pick_tab)
        tabs_row = QHBoxLayout()
        tabs_row.addWidget(self.tabs)
        tabs_row.addStretch(1)
        lay.addLayout(tabs_row)

        # The bar for ticked rows.
        self.bulk = QFrame()
        self.bulk.setObjectName("BulkBar")
        bl = QHBoxLayout(self.bulk)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(8)
        self.bulk_label = label("", "Strong")
        bl.addWidget(self.bulk_label)
        self.apply_all_btn = button("Apply to all", "Primary", self._apply_checked)
        bl.addWidget(self.apply_all_btn)
        self.download_btn = button("Download resumes", "", self._download_checked)
        bl.addWidget(self.download_btn)
        bl.addWidget(button("Clear", "", self._clear_checked))
        bl.addWidget(label("Each job opens in its own Chrome tab. Press Alt+V there to fill it.", "Muted", wrap=True), 1)
        self.bulk.hide()
        lay.addWidget(self.bulk)

        card = QFrame()
        card.setObjectName("TableCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(1, 1, 1, 1)
        card_lay.setSpacing(0)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setFixedHeight(42)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.select_all = QCheckBox(hh)
        self.select_all.setToolTip("Select every Ready job on this page")
        self.select_all.toggled.connect(self._toggle_all)
        self.select_all.hide()
        hh.sectionResized.connect(lambda *_a: self._place_select_all())
        hh.geometriesChanged.connect(self._place_select_all)
        card_lay.addWidget(self.table)
        self.empty = label("", "Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(80)
        self.empty.hide()
        card_lay.addWidget(self.empty)
        lay.addWidget(card, 1)

        pager = QHBoxLayout()
        pager.setSpacing(6)
        self.page_info = label("", "Strong")
        pager.addWidget(self.page_info)
        self.per_page = label("", "Muted")
        pager.addWidget(self.per_page)
        pager.addWidget(button("change in Settings", "TextLink", self.open_settings.emit))
        pager.addStretch(1)
        self.prev_btn = button("Prev", "Page", lambda: self._go(self.page - 1))
        pager.addWidget(self.prev_btn)
        self.pages_box = QHBoxLayout()
        self.pages_box.setSpacing(6)
        pager.addLayout(self.pages_box)
        self.next_btn = button("Next", "Page", lambda: self._go(self.page + 1))
        self.next_btn.setLayoutDirection(Qt.RightToLeft)
        pager.addWidget(self.next_btn)
        lay.addLayout(pager)

        self.toast = Toast()
        self.toast.undo.connect(self._run_undo)
        lay.addWidget(self.toast)
        self._style_icons()

        state.profile_changed.connect(lambda _p: self.reload(reset_page=True))
        state.data_changed.connect(self.reload)
        maker.job_changed.connect(lambda _j: self._refresh_doc_cells())
        maker.state_changed.connect(lambda _r: self._refresh_doc_cells())
        maker.made.connect(lambda _c: self.reload())

        self._poll = QTimer(self)
        self._poll.setInterval(20_000)
        self._poll.timeout.connect(self._check_version)
        self._poll.start()

    # ------------------------------------------------------------------ loading
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if config.page_size != getattr(self, "_shown_page_size", None):
            self.reload(reset_page=True)

    def set_tab(self, tab: str) -> None:
        self._pick_tab(tab)
        self.tabs.set_current(tab)

    def _pick_tab(self, tab: str) -> None:
        self._auto_tab = False
        self.tab = tab
        self.checked.clear()
        self.reload(reset_page=True)

    def _go(self, page: int) -> None:
        if 1 <= page <= self.total_pages and page != self.page:
            self.page = page
            self.reload()

    def _query(self) -> dict:
        return next(q for key, _t, q in TABS if key == self.tab)

    def reload(self, reset_page: bool = False) -> None:
        if reset_page:
            self.page = 1
        if not self.state.profiles and self.state.session.mode == "token":
            return
        self._load_seq += 1
        seq = self._load_seq
        size = config.page_size
        self._shown_page_size = size
        profile = self.state.request_profile
        query = self._query()
        search = self._search_text
        page = self.page
        api = self.state.api

        def fetch():
            params = {"page": page, "pageSize": size, "sort": "number"}
            if query.get("statuses"):
                params["statuses"] = ",".join(query["statuses"])
            if query.get("hasResume"):
                params["hasResume"] = query["hasResume"]
            if search:
                params["search"] = search
            if profile and api.session.mode == "account":
                params["profileId"] = profile
            data = api.request("GET", "/api/bids", params=params, profile_id=profile)
            version = ""
            try:
                version = api.bids_version(profile)
            except Exception:  # noqa: BLE001 - the version is only for auto-refresh
                pass
            return data, version

        tasks.run(fetch, lambda result: self._loaded(seq, *result), self._failed, owner=self)
        self._load_counts(profile)

    def _load_counts(self, profile: str | None) -> None:
        api = self.state.api

        def fetch():
            counts = {}
            for key, _t, q in TABS:
                params = {"page": 1, "pageSize": 1}
                if q.get("statuses"):
                    params["statuses"] = ",".join(q["statuses"])
                if q.get("hasResume"):
                    params["hasResume"] = q["hasResume"]
                if profile and api.session.mode == "account":
                    params["profileId"] = profile
                data = api.request("GET", "/api/bids", params=params, profile_id=profile)
                counts[key] = int((data or {}).get("total", 0))
            return counts

        tasks.run(fetch, self._counts_loaded, lambda _e: None, owner=self)

    def _counts_loaded(self, counts: dict) -> None:
        self.tabs.set_counts(counts)
        self.counts_changed.emit(counts)
        if self._auto_tab:
            self._auto_tab = False
            if self.tab == "ready" and not counts.get("ready"):
                self.set_tab("draft")

    def _loaded(self, seq: int, data: dict, version: str) -> None:
        if seq != self._load_seq:
            return
        self.state.mark_online()
        self._version = version
        self.rows = list((data or {}).get("items", []))
        self.total = int((data or {}).get("total", len(self.rows)))
        self.total_pages = max(1, int((data or {}).get("totalPages", 1)))
        self.page = min(self.page, self.total_pages)
        self._render()

    def _failed(self, error: Exception) -> None:
        self.state.report_error(error)
        self.rows = []
        self.total = 0
        self._render(message=getattr(error, "message", str(error)))

    def _check_version(self) -> None:
        if not self.isVisible() or not self._version:
            return
        profile = self.state.request_profile

        def changed(version: str) -> None:
            if version and version != self._version:
                self.reload()

        tasks.run(lambda: self.state.api.bids_version(profile), changed, self.state.report_error, owner=self)

    # ------------------------------------------------------------------ table
    def set_search(self, text: str) -> None:
        """The top bar's search box."""
        self._search_text = text.strip()
        self._search_timer.start()

    def _style_icons(self) -> None:
        """Icons in the current theme's colours (called again after a theme change)."""
        with_icon(self.prev_btn, "chevron-left", "text", 14)
        with_icon(self.next_btn, "chevron-right", "text", 14)
        with_icon(self.add_btn, "plus")
        with_icon(self.download_btn, "download")
        with_icon(self.apply_all_btn, "play", "accent_fg", 11)
        with_icon(self.refresh_btn, "refresh", "text", 16)

    def _add_job(self) -> None:
        chrome.open_url(f"{self.state.session.server}/applications/new")

    def _render(self, message: str = "") -> None:
        c = theme.colors()
        self._style_icons()
        self.tabs.set_current(self.tab)
        show_profile = not self.state.profile_id and self.state.session.mode == "account"
        cols = list(COLUMNS)
        if show_profile:
            cols.insert(2, "Profile")
        self.table.clear()
        self.table.setColumnCount(len(cols))
        for i, name in enumerate(cols):
            head = QTableWidgetItem(name.upper())
            head.setTextAlignment((Qt.AlignHCenter if name in CENTERED else Qt.AlignLeft) | Qt.AlignVCenter)
            self.table.setHorizontalHeaderItem(i, head)
        self._col = {name: i for i, name in enumerate(cols)}
        self.table.setRowCount(len(self.rows))
        self._company_labels: list[tuple[QLabel, str]] = []
        for r, bid in enumerate(self.rows):
            self._fill_row(r, bid, show_profile, c)
        self._fit_columns()

        self.table.setVisible(bool(self.rows))
        self.empty.setVisible(not self.rows)
        self.empty.setText(message or "No applications here yet.")
        start = (self.page - 1) * config.page_size + 1 if self.rows else 0
        end = start + len(self.rows) - 1 if self.rows else 0
        self.page_info.setText(f"Showing {start}–{end} of {self.total:,}" if self.rows else "No applications")
        self.per_page.setText(f"  {config.page_size} per page ·")
        self._render_pages()
        self._update_bulk()
        self._place_select_all()

    def _fill_row(self, r: int, bid: dict, show_profile: bool, c: dict) -> None:
        col = self._col
        bid_id = bid["id"]
        label_text, kind = display_status(bid)

        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setAlignment(Qt.AlignCenter)
        if kind == "ready":
            cb = QCheckBox()
            cb.setChecked(bid_id in self.checked)
            cb.setToolTip(f"Select {bid.get('company', '')}")
            cb.toggled.connect(lambda on, i=bid_id: self._toggle(i, on))
            bl.addWidget(cb)
        self.table.setCellWidget(r, col[""], box)

        who = QWidget()
        wl = QVBoxLayout(who)
        wl.setContentsMargins(3, 0, 6, 0)
        wl.setSpacing(1)
        wl.setAlignment(Qt.AlignVCenter)
        name = QLabel(str(bid.get("company", "")))
        name.setObjectName("Strong")
        name.setToolTip(name.text())
        self._company_labels.append((name, name.text()))
        wl.addWidget(name)
        wl.addWidget(label(f"#{bid.get('number', '')}", "Faint"))
        self.table.setCellWidget(r, col["Company"], who)
        if show_profile:
            self.table.setItem(r, col["Profile"], self._item((bid.get("candidate") or {}).get("displayName", ""), c["muted"]))
        role = self._item(str(bid.get("role", "")), c["text"])
        role.setToolTip(role.text())
        self.table.setItem(r, col["Role"], role)
        location = self._item(str(bid.get("location", "")), c["muted"])
        location.setToolTip(location.text())
        self.table.setItem(r, col["Location"], location)
        found = self._item(_short_date(bid.get("bidDate")), c["muted"])
        found.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, col["Found"], found)

        chip_box = QWidget()
        cl = QHBoxLayout(chip_box)
        cl.setContentsMargins(0, 0, 0, 0)
        chip = Chip(label_text, kind, clickable=True)
        chip.setToolTip("Change status")
        chip.clicked.connect(lambda _=False, b=bid, w=chip: self._status_menu(b, w))
        cl.addStretch(1)
        cl.addWidget(chip)
        cl.addStretch(1)
        self.table.setCellWidget(r, col["Status"], chip_box)

        self.table.setCellWidget(r, col["Resume"], self._doc_cell(bid, "resume"))
        self.table.setCellWidget(r, col["Cover letter"], self._doc_cell(bid, "cover-letter"))

        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)
        al.addStretch(1)
        open_btn = icon_button("external", "Open job post", lambda _=False, b=bid: self._open_job(b))
        open_btn.setEnabled(bool(bid.get("jobUrl")))
        al.addWidget(open_btn)
        if kind == "ready":
            apply_btn = with_icon(button("Apply", "Primary", lambda _=False, b=bid: self._apply([b]),
                                         f"Apply to {bid.get('company', '')}"), "play", "accent_fg", 11)
            apply_btn.setFixedHeight(32)
            al.addWidget(apply_btn)
        elif bid.get("status") == "Draft":
            off = button("Apply", "Primary", None, "Resume not ready yet")
            off.setFixedHeight(32)
            off.setEnabled(False)
            al.addWidget(off)
        else:
            al.addWidget(self._state_label("check", "Applied", c["muted"], c["muted"]))
        al.addStretch(1)
        self.table.setCellWidget(r, col["Actions"], actions)

    @staticmethod
    def _item(text: str, color: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return item

    @staticmethod
    def _state_label(icon_name: str, text: str, icon_color: str, text_color: str, bold: bool = False) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        pic = QLabel()
        pic.setPixmap(pixmap(icon_name, icon_color, 15, 2.2))
        lay.addWidget(pic)
        words = QLabel(text)
        words.setStyleSheet(f"color: {text_color}; font-weight: {600 if bold else 500};")
        lay.addWidget(words)
        return box

    def _doc_cell(self, bid: dict, kind: str) -> QWidget:
        c = theme.colors()
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        has = bool(bid.get("hasResume") if kind == "resume" else bid.get("hasCoverLetter"))
        if has:
            link = button("Ready", "Ghost", lambda _=False, b=bid, k=kind: self._view(b, k),
                          "Open the preview (PDF / Word download)")
            link.setIcon(QIcon(pixmap("check", c["ok"], 15, 2.4)))
            link.setIconSize(QSize(15, 15))
            link.setStyleSheet(f"QPushButton {{ color: {c['text']}; font-weight: 500; }}")
            lay.addWidget(link)
        else:
            job = self.maker.job
            if job and str(job.number) == str(bid.get("number")) and bid.get("status") == "Draft":
                lay.addWidget(self._state_label("spinner", "Making…", c["accent"], c["accent"], True))
            elif self.maker.running and bid.get("status") == "Draft" and not bid.get("hasResume"):
                lay.addWidget(self._state_label("clock", "In queue", c["muted"], c["muted"]))
            else:
                lay.addWidget(label("—", "Faint"))
        lay.addStretch(1)
        return box

    def _refresh_doc_cells(self) -> None:
        if not self._col:
            return
        for r, bid in enumerate(self.rows):
            self.table.setCellWidget(r, self._col["Resume"], self._doc_cell(bid, "resume"))
            self.table.setCellWidget(r, self._col["Cover letter"], self._doc_cell(bid, "cover-letter"))

    def _fit_columns(self) -> None:
        """Fixed columns keep their width; Company, Profile, Role and Location share the rest."""
        if not self._col:
            return
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Fixed)
        spare = self.table.viewport().width() - sum(FIXED.get(n, 0) for n in self._col)
        flex = [n for n in self._col if n in SHARE]
        total = sum(SHARE[n] for n in flex) or 1
        for name, i in self._col.items():
            if name in SHARE:
                width = max(MINIMUM[name], int(spare * SHARE[name] / total))
            else:
                width = FIXED.get(name, 110)
            self.table.setColumnWidth(i, width)
        # Long company names end in "…" (the full name is in the tooltip).
        room = self.table.columnWidth(self._col["Company"]) - 14
        for name_label, full in getattr(self, "_company_labels", []):
            name_label.setText(name_label.fontMetrics().elidedText(full, Qt.ElideRight, room))
        self._place_select_all()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_columns)

    def _render_pages(self) -> None:
        while self.pages_box.count():
            item = self.pages_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for p in _page_window(self.page, self.total_pages):
            if p is None:
                self.pages_box.addWidget(label("…", "Muted"))
                continue
            btn = button(str(p), "Page", lambda _=False, n=p: self._go(n))
            btn.setCheckable(True)
            btn.setChecked(p == self.page)
            self.pages_box.addWidget(btn)
        self.prev_btn.setEnabled(self.page > 1)
        self.next_btn.setEnabled(self.page < self.total_pages)

    def _place_select_all(self) -> None:
        ready = [b for b in self.rows if display_status(b)[1] == "ready"]
        if not self._col or not ready or not self.table.isVisible():
            self.select_all.hide()
            return
        hh = self.table.horizontalHeader()
        x = hh.sectionViewportPosition(self._col[""])
        size = self.select_all.sizeHint()
        self.select_all.move(x + (hh.sectionSize(self._col[""]) - size.width()) // 2, (hh.height() - size.height()) // 2)
        self.select_all.blockSignals(True)
        self.select_all.setChecked(all(b["id"] in self.checked for b in ready))
        self.select_all.blockSignals(False)
        self.select_all.show()
        self.select_all.raise_()

    def _toggle_all(self, on: bool) -> None:
        ready = {b["id"] for b in self.rows if display_status(b)[1] == "ready"}
        if on:
            self.checked |= ready
        else:
            self.checked -= ready
        self._render()

    # ------------------------------------------------------------------ actions
    def _toggle(self, bid_id: str, on: bool) -> None:
        (self.checked.add if on else self.checked.discard)(bid_id)
        self._update_bulk()

    def _update_bulk(self) -> None:
        visible = {b["id"] for b in self.rows}
        self.checked &= visible
        n = len(self.checked)
        self.bulk.setVisible(n > 0)
        self.bulk_label.setText(f"{n} selected")
        self.apply_all_btn.setText(f"Apply to all {n}")

    def _clear_checked(self) -> None:
        self.checked.clear()
        self._render()

    def _selected_bids(self) -> list[dict]:
        return [b for b in self.rows if b["id"] in self.checked]

    def _apply_checked(self) -> None:
        self._apply(self._selected_bids())

    def _apply(self, bids: list[dict]) -> None:
        bids = [b for b in bids if b.get("jobUrl")]
        if not bids:
            self.toast.show_message("These applications have no job link.")
            return
        chrome.apply([b["id"] for b in bids])
        what = bids[0]["company"] if len(bids) == 1 else f"{len(bids)} jobs"
        where = "in Chrome" if len(bids) == 1 else "in Chrome tabs"
        self._change_status(bids, "Applied",
                            f"Opened {what} {where}. Press Alt+V to fill the form, then Submit. Marked as Applied.")
        self.checked -= {b["id"] for b in bids}

    def _open_job(self, bid: dict) -> None:
        if bid.get("jobUrl"):
            chrome.open_url(bid["jobUrl"])

    def _view(self, bid: dict, kind: str) -> None:
        DocViewer(self.state, bid, kind, self).exec()

    def _status_menu(self, bid: dict, anchor: QPushButton) -> None:
        menu = QMenu(self)
        current = bid.get("status")
        for status in STATUSES:
            if status in GROUP_STARTS:
                menu.addSeparator()
            action = QAction(("✓  " if status == current else "     ") + status, menu)
            action.triggered.connect(lambda _=False, s=status: self._change_status([bid], s, None))
            menu.addAction(action)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _change_status(self, bids: list[dict], status: str, message: str | None) -> None:
        if not bids:
            return
        previous = {b["id"]: b.get("status", "Draft") for b in bids}
        ids = list(previous)
        profile = self._profile_for(bids)
        api = self.state.api

        def done(_n) -> None:
            text = message or f"{bids[0]['company']}: status changed to {status}."
            self._undo = lambda: self._restore(previous, profile)
            self.toast.show_message(text, can_undo=True)
            self.state.data_changed.emit()

        def failed(error: Exception) -> None:
            self.state.report_error(error)
            QMessageBox.warning(self, "Could not change the status", getattr(error, "message", str(error)))

        tasks.run(lambda: api.set_status(ids, status, profile), done, failed, owner=self)

    def _restore(self, previous: dict[str, str], profile: str | None) -> None:
        api = self.state.api
        by_status: dict[str, list[str]] = {}
        for bid_id, status in previous.items():
            by_status.setdefault(status, []).append(bid_id)

        def run():
            for status, ids in by_status.items():
                api.set_status(ids, status, profile)

        tasks.run(run, lambda _r: (self.toast.show_message("Undone."), self.state.data_changed.emit()),
                  lambda e: QMessageBox.warning(self, "Could not undo", getattr(e, "message", str(e))), owner=self)

    def _run_undo(self) -> None:
        if self._undo:
            undo, self._undo = self._undo, None
            undo()

    def _profile_for(self, bids: list[dict]) -> str | None:
        if self.state.session.mode == "token":
            return (bids[0].get("candidate") or {}).get("profileId") or self.state.request_profile
        return self.state.request_profile

    def _download_checked(self) -> None:
        bids = [b for b in self._selected_bids() if b.get("hasResume")]
        if not bids:
            return
        folder = QFileDialog.getExistingDirectory(self, "Save the resumes in…")
        if not folder:
            return
        api = self.state.api

        def run():
            saved = 0
            for b in bids:
                profile = (b.get("candidate") or {}).get("profileId") or self.state.request_profile
                data, name = api.document(b["id"], "resume", "pdf", profile)
                target = Path(folder) / f"{_safe(b.get('company', 'company'))} - {name}"
                target.write_bytes(data)
                saved += 1
            return saved

        tasks.run(run, lambda n: self.toast.show_message(f"Saved {n} resume(s) to {folder}."),
                  lambda e: QMessageBox.warning(self, "Download failed", getattr(e, "message", str(e))), owner=self)


def _short_date(value) -> str:
    text = str(value or "")[:10]
    if len(text) == 10:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        try:
            return f"{months[int(text[5:7]) - 1]} {int(text[8:10])}"
        except (ValueError, IndexError):
            return text
    return text


def _page_window(page: int, total: int) -> list[int | None]:
    if total <= 7:
        return list(range(1, total + 1))
    pages: list[int | None] = [1]
    start, end = max(2, page - 1), min(total - 1, page + 1)
    if start > 2:
        pages.append(None)
    pages.extend(range(start, end + 1))
    if end < total - 1:
        pages.append(None)
    pages.append(total)
    return pages


def _safe(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum() or ch in " -_").strip()[:60] or "file"

