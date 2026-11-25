"""Home: today's numbers, what needs attention, and the Resume Maker at a glance."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from .. import tasks
from ..state import AppState
from ..statuses import display_status
from .widgets import Card, Dot, button, hline, label, stat_card


class HomePage(QWidget):
    go_tab = Signal(str)
    go_maker = Signal()

    def __init__(self, state: AppState, maker):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.maker = maker

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(18)
        self.greeting = label("", "Title")
        lay.addWidget(self.greeting)
        self.sub = label("", "Subtitle")
        lay.addWidget(self.sub)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.stats = {}
        for i, (key, title) in enumerate((("draft", "Waiting for a resume"), ("ready", "Ready to apply"),
                                          ("applied", "Applied"), ("interview", "Interviews"))):
            card, value, note = stat_card(title)
            self.stats[key] = (value, note)
            grid.addWidget(card, 0, i)
        lay.addLayout(grid)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.attention = Card("Needs your attention")
        self.attention_box = QVBoxLayout()
        self.attention_box.setSpacing(10)
        self.attention.body.addLayout(self.attention_box)
        self.attention.body.addStretch(1)
        row.addWidget(self.attention, 3)

        right = QVBoxLayout()
        right.setSpacing(16)
        maker_card = Card("Resume Maker")
        status_row = QHBoxLayout()
        self.maker_dot = Dot("#9AA3B2", 11)
        status_row.addWidget(self.maker_dot)
        self.maker_status = label("", "")
        self.maker_status.setStyleSheet("font-size: 13pt; font-weight: 700;")
        status_row.addWidget(self.maker_status)
        status_row.addStretch(1)
        status_row.addWidget(button("Open", "Link", self.go_maker.emit))
        maker_card.body.addLayout(status_row)
        self.maker_note = label("", "Muted", wrap=True)
        maker_card.body.addWidget(self.maker_note)
        self.maker_btn = button("", "Primary", self._toggle_maker)
        maker_card.body.addWidget(self.maker_btn)
        right.addWidget(maker_card)

        self.recent = Card("Newest applications")
        self.recent_box = QVBoxLayout()
        self.recent.body.addLayout(self.recent_box)
        right.addWidget(self.recent)
        right.addStretch(1)
        row.addLayout(right, 2)
        lay.addLayout(row, 1)

        state.profile_changed.connect(lambda _p: self.reload())
        state.data_changed.connect(self.reload)
        maker.state_changed.connect(lambda _r: self._show_maker())
        maker.job_changed.connect(lambda _j: self._show_maker())
        maker.made.connect(lambda _c: self.reload())
        self._show_maker()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        hour = datetime.now().hour
        part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        name = self.state.session.display_name if self.state.session.mode == "account" else ""
        self.greeting.setText(f"Good {part}{', ' + name if name else ''}")
        self.sub.setText(f"{datetime.now():%A, %B %d} · Profile: {self.state.profile_name}")
        api, profile = self.state.api, self.state.request_profile

        def fetch():
            from ..statuses import TABS

            counts = {}
            for key, _t, q in TABS:
                if key in ("all", "remake"):
                    continue
                params = {"page": 1, "pageSize": 1}
                if q.get("statuses"):
                    params["statuses"] = ",".join(q["statuses"])
                for name in ("hasResume", "needsRemake"):
                    if q.get(name):
                        params[name] = q[name]
                if profile and api.session.mode == "account":
                    params["profileId"] = profile
                counts[key] = int((api.request("GET", "/api/bids", params=params, profile_id=profile) or {}).get("total", 0))
            recent_params = {"page": 1, "pageSize": 5, "sort": "bidDate"}
            if profile and api.session.mode == "account":
                recent_params["profileId"] = profile
            recent = (api.request("GET", "/api/bids", params=recent_params, profile_id=profile) or {}).get("items", [])
            return counts, recent

        tasks.run(fetch, lambda r: self._show(*r), self.state.report_error, owner=self)

    def _show(self, counts: dict, recent: list[dict]) -> None:
        self.state.mark_online()
        notes = {"draft": "The Resume Maker makes these", "ready": "Resume and cover letter are made",
                 "applied": "Waiting for an answer", "interview": "Screening to final, and offers"}
        for key, (value, note) in self.stats.items():
            value.setText(str(counts.get(key, 0)))
            note.setText(notes[key])

        _clear(self.attention_box)
        items = []
        if counts.get("ready"):
            items.append((f"{counts['ready']} application(s) are ready to apply", "Press Apply in each row, or tick several and Apply to all.",
                          "Go to Ready", lambda: self.go_tab.emit("ready")))
        if counts.get("draft") and not self.maker.running:
            items.append((f"{counts['draft']} Draft(s) are waiting for a resume", "The Resume Maker is stopped.",
                          "Start Resume Maker", self._toggle_maker))
        if counts.get("interview"):
            items.append((f"{counts['interview']} application(s) are in interviews", "Keep their statuses up to date.",
                          "Open Interviews", lambda: self.go_tab.emit("interview")))
        if not items:
            self.attention_box.addWidget(label("Nothing needs you right now.", "Muted"))
        for i, (title, note, action, fn) in enumerate(items):
            if i:
                self.attention_box.addWidget(hline())
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(2)
            t = label(title, "")
            t.setStyleSheet("font-weight: 600;")
            text.addWidget(t)
            text.addWidget(label(note, "Muted", wrap=True))
            row.addLayout(text, 1)
            row.addWidget(button(action, "Primary" if i == 0 else "", fn))
            self.attention_box.addLayout(row)

        _clear(self.recent_box)
        if not recent:
            self.recent_box.addWidget(label("No applications yet.", "Muted"))
        for bid in recent:
            row = QHBoxLayout()
            name = label(f"{bid.get('company', '')} · {bid.get('role', '')}", "")
            name.setWordWrap(True)
            row.addWidget(name, 1)
            row.addWidget(label(display_status(bid)[0], "Muted"))
            self.recent_box.addLayout(row)

    def _show_maker(self) -> None:
        running = self.maker.running
        self.maker_dot.set_color("#22C55E" if running else "#9AA3B2")
        self.maker_status.setText(f"Running with {self.maker.ai_name()}" if running else "Stopped")
        job = self.maker.job
        if running:
            self.maker_note.setText(f"Making #{job.number} {job.company}" if job else "Waiting for the next Draft")
        else:
            self.maker_note.setText("Start it to make the resumes and cover letters for your Drafts.")
        self.maker_btn.setText("■  Stop" if running else "▶  Start")
        self.maker_btn.setObjectName("" if running else "Primary")
        self.maker_btn.style().unpolish(self.maker_btn)
        self.maker_btn.style().polish(self.maker_btn)

    def _toggle_maker(self) -> None:
        if self.maker.running:
            self.maker.stop()
        else:
            self.maker.start(self.state.request_profile if self.state.session.mode == "token" else None)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())

