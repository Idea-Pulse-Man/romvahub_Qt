"""Resume Maker: Start / Stop, the AI website, what is being made now, and the log."""

from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from ..config import AI_SITES, CHATGPT_EFFORTS, CHATGPT_MODELS, CHATGPT_MODES, bundled_agent_dir, config
from ..maker import Maker, node_path
from ..state import AppState
from .resume_actions import ResumeCheckCard
from .widgets import Card, Dot, Segmented, button, label, page_header

STEPS = ["Read the job post", "Write the resume", "Write the cover letter", "Build the Word and PDF files",
         "Save to romva and check it"]


class ResumeMakerPage(QWidget):
    def __init__(self, state: AppState, maker: Maker):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.maker = maker

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
        lay.addWidget(page_header("Resume Maker", "Makes the resume and cover letter for each new Draft, one by one, "
                                                  "with your own signed-in AI website. No API key needed."))

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)

        # Start / Stop.
        control = Card()
        top = QHBoxLayout()
        text = QVBoxLayout()
        status_row = QHBoxLayout()
        self.dot = Dot("#9AA3B2", 12)
        status_row.addWidget(self.dot)
        self.status = label("Stopped", "")
        self.status.setStyleSheet("font-size: 15pt; font-weight: 700;")
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        text.addLayout(status_row)
        self.status_note = label("", "Muted", wrap=True)
        text.addWidget(self.status_note)
        top.addLayout(text, 1)
        self.toggle_btn = button("▶  Start", "Primary", self._toggle)
        self.toggle_btn.setMinimumHeight(46)
        self.toggle_btn.setMinimumWidth(130)
        top.addWidget(self.toggle_btn)
        control.body.addLayout(top)
        self.problem = label("", "Error", wrap=True)
        self.problem.hide()
        control.body.addWidget(self.problem)
        counts = QHBoxLayout()
        self.made = label("0", "Big")
        self.failed = label("0", "Big")
        for value, title in ((self.made, "Made since the app started"), (self.failed, "Failed")):
            box = QVBoxLayout()
            box.addWidget(value)
            box.addWidget(label(title, "Muted"))
            counts.addLayout(box)
        counts.addStretch(1)
        control.body.addLayout(counts)
        left.addWidget(control)

        # The AI website, and which Profile in token mode.
        ai = Card("AI website")
        self.ai = Segmented([(key, f"{name}  ·  {site}") for key, name, site in AI_SITES], config.maker_ai)
        self.ai.changed.connect(self._pick_ai)
        ai.body.addWidget(self.ai)
        ai.body.addWidget(label("The work happens in a small Chrome window that uses your own account on that site. "
                                "Sign in there once.", "Muted", wrap=True))
        # ChatGPT only: Chat / Work, the model and the thinking effort, chosen in every chat.
        self.chatgpt_box = QWidget()
        gpt = QVBoxLayout(self.chatgpt_box)
        gpt.setContentsMargins(0, 4, 0, 0)
        gpt.setSpacing(8)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._row_label("ChatGPT mode", "Label"))
        self.chatgpt_mode = Segmented(list(CHATGPT_MODES), config.chatgpt_mode)
        self.chatgpt_mode.changed.connect(self._pick_chatgpt_mode)
        mode_row.addWidget(self.chatgpt_mode)
        mode_row.addStretch(1)
        gpt.addLayout(mode_row)
        model_row = QHBoxLayout()
        model_row.addWidget(self._row_label("Model", "Label"))
        self.chatgpt_model = QComboBox()
        self.chatgpt_model.setEditable(True)
        self.chatgpt_model.setInsertPolicy(QComboBox.NoInsert)
        self.chatgpt_model.setMinimumWidth(220)
        self.chatgpt_model.setToolTip("The model as ChatGPT's model menu names it. Another name can be typed in.")
        self.chatgpt_model.currentTextChanged.connect(
            lambda text: config.set_chatgpt_model(config.chatgpt_mode, text) if not self._filling_models else None)
        model_row.addWidget(self.chatgpt_model)
        model_row.addStretch(1)
        gpt.addLayout(model_row)
        effort_row = QHBoxLayout()
        effort_row.addWidget(self._row_label("Effort", "Label"))
        self.chatgpt_effort = Segmented(list(CHATGPT_EFFORTS), config.chatgpt_effort)
        self.chatgpt_effort.changed.connect(lambda key: setattr(config, "chatgpt_effort", key))
        effort_row.addWidget(self.chatgpt_effort)
        effort_row.addStretch(1)
        gpt.addLayout(effort_row)
        self.chatgpt_note = label("", "Muted", wrap=True)
        gpt.addWidget(self.chatgpt_note)
        ai.body.addWidget(self.chatgpt_box)
        self._filling_models = False
        self._fill_models()

        self.profile_row = QHBoxLayout()
        self.profile_row.addWidget(label("Make for", "Label"))
        self.profile_pick = QComboBox()
        self.profile_row.addWidget(self.profile_pick, 1)
        ai.body.addLayout(self.profile_row)
        self.scope_note = label("", "Muted", wrap=True)
        ai.body.addWidget(self.scope_note)
        left.addWidget(ai)

        # The Resume check: flagged Drafts, Check all, Remake.
        self.check_card = ResumeCheckCard(state, maker)
        self.check_card.open_doc.connect(self._open_doc)
        left.addWidget(self.check_card)

        # Now making.
        now = Card("Now making")
        self.job_title = label("Nothing is being made right now.", "")
        self.job_title.setStyleSheet("font-size: 12pt; font-weight: 700;")
        now.body.addWidget(self.job_title)
        self.job_role = label("", "Muted")
        now.body.addWidget(self.job_role)
        self.step_labels = []
        for step in STEPS:
            lab = label(f"○  {step}", "Muted")
            self.step_labels.append(lab)
            now.body.addWidget(lab)
        left.addWidget(now)

        # The agent itself.
        setup = Card("Agent")
        self.agent_dir = label("", "Muted", wrap=True)
        setup.body.addWidget(self.agent_dir)
        row = QHBoxLayout()
        self.choose_btn = button("Choose folder…", "", self._choose_dir)
        self.install_btn = button("Install / Update", "", self.maker.install)
        row.addWidget(self.choose_btn)
        row.addWidget(self.install_btn)
        row.addStretch(1)
        setup.body.addLayout(row)
        self.node = label("", "Muted")
        setup.body.addWidget(self.node)
        left.addWidget(setup)
        # The built RomvaHub.exe carries the agent and Node.js: nothing to choose or install.
        self.bundled = bool(bundled_agent_dir())
        self.choose_btn.setVisible(not self.bundled)
        self.install_btn.setVisible(not self.bundled)
        self.node.setVisible(not self.bundled)
        left.addStretch(1)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(16)
        log_card = Card("Activity log")
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(380)
        log_card.body.addWidget(self.log)
        log_card.body.addWidget(button("Copy log", "", lambda: self._copy_log()))
        right.addWidget(log_card, 1)

        opts = Card("Options")
        self.autostart = QCheckBox("Start the Resume Maker when the app starts")
        self.autostart.setChecked(config.maker_autostart)
        self.autostart.toggled.connect(lambda on: setattr(config, "maker_autostart", on))
        opts.body.addWidget(self.autostart)
        self.notify = QCheckBox("Show a pop-up when a resume is ready")
        self.notify.setChecked(config.notify_ready)
        self.notify.toggled.connect(lambda on: setattr(config, "notify_ready", on))
        opts.body.addWidget(self.notify)
        right.addWidget(opts)
        cols.addLayout(right, 2)
        lay.addLayout(cols)

        maker.state_changed.connect(lambda _r: self._show())
        maker.job_changed.connect(lambda _j: self._show())
        maker.line.connect(self._add_line)
        maker.problem.connect(self._show_problem)
        state.profiles_changed.connect(self._fill_profiles)
        for stamp, level, text_ in maker.lines:
            self._add_line(stamp, level, text_)
        self._fill_profiles()
        self._show()

    def _fill_profiles(self) -> None:
        token_mode = self.state.session.mode == "token"
        self.profile_pick.clear()
        for p in self.state.profiles:
            if not p.get("revoked"):
                self.profile_pick.addItem(p["name"], p["id"])
        if token_mode and self.state.profile_id:
            index = self.profile_pick.findData(self.state.profile_id)
            if index >= 0:
                self.profile_pick.setCurrentIndex(index)
        for i in range(self.profile_row.count()):
            widget = self.profile_row.itemAt(i).widget()
            if widget:
                widget.setVisible(token_mode)
        self.scope_note.setText(
            "One Profile at a time: the agent works as that Profile's token." if token_mode
            else ("It makes resumes for every Profile in your reach (as an admin: all Profiles)."
                  if self.state.session.is_admin else "It makes resumes for every Profile assigned to you.")
        )

    def _show(self) -> None:
        running = self.maker.running
        self.dot.set_color("#22C55E" if running else "#9AA3B2")
        self.status.setText("Running" if running else "Stopped")
        self.status_note.setText(
            f"Working through your Drafts with {self.maker.ai_name()}. You can close this window; it keeps going in the tray."
            if running else "Press Start to make the resumes for your Drafts."
        )
        self.toggle_btn.setText("■  Stop" if running else "▶  Start")
        self.toggle_btn.setObjectName("" if running else "Primary")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)
        self.made.setText(str(self.maker.made_today))
        self.failed.setText(str(self.maker.failed_today))
        self.ai.setEnabled(not running)
        self.chatgpt_box.setEnabled(not running)
        self.profile_pick.setEnabled(not running)
        job = self.maker.job
        if job:
            self.job_title.setText(f"#{job.number} {job.company}")
            self.job_role.setText(job.role)
        else:
            self.job_title.setText("Nothing is being made right now.")
            self.job_role.setText("Waiting for the next Draft." if running else "")
        for i, lab in enumerate(self.step_labels, start=1):
            if job and i < job.step:
                lab.setText(f"✓  {STEPS[i - 1]}")
                lab.setObjectName("Ok")
            elif job and i == job.step:
                lab.setText(f"…  {STEPS[i - 1]}")
                lab.setObjectName("")
            else:
                lab.setText(f"○  {STEPS[i - 1]}")
                lab.setObjectName("Muted")
            lab.style().unpolish(lab)
            lab.style().polish(lab)
        if self.bundled:
            self.agent_dir.setText("Built into the app (with its own Node.js). Nothing to install: "
                                   "just sign in to the AI website in its Chrome window the first time.")
            return
        self.agent_dir.setText(f"Folder: {self.maker.agent_dir or '(not found)'}")
        self.node.setText(f"Node.js: {node_path() or 'not found — install it from nodejs.org'}")

    def _toggle(self) -> None:
        self.problem.hide()
        if self.maker.running:
            self.maker.stop()
        else:
            profile = self.profile_pick.currentData() if self.state.session.mode == "token" else None
            self.maker.start(profile)

    def _open_doc(self, bid: dict, kind: str) -> None:
        from .doc_viewer import DocViewer

        DocViewer(self.state, bid, kind, self).exec()

    @staticmethod
    def _row_label(text: str, kind: str):
        lab = label(text, kind)
        lab.setMinimumWidth(96)
        return lab

    def _pick_ai(self, key: str) -> None:
        config.maker_ai = key
        self.chatgpt_box.setVisible(key == "chatgpt")

    def _pick_chatgpt_mode(self, key: str) -> None:
        config.chatgpt_mode = key
        self._fill_models()

    def _fill_models(self) -> None:
        """The models of the chosen mode, with the one saved for it (a typed-in name too)."""
        mode = config.chatgpt_mode
        saved = config.chatgpt_model(mode)
        self._filling_models = True
        try:
            self.chatgpt_model.clear()
            self.chatgpt_model.addItems(list(CHATGPT_MODELS[mode]))
            self.chatgpt_model.setCurrentText(saved)
        finally:
            self._filling_models = False
        self.chatgpt_box.setVisible(config.maker_ai == "chatgpt")
        self.chatgpt_note.setText(
            "Work chats are ordinary chats and stay in your ChatGPT history (ChatGPT has no Work mode in a "
            "temporary chat), and Work mode has no Web search switch. A model without the effort chosen gets the "
            "nearest level below it." if mode == "work" else
            "Temporary chats, with Web search on. Chat mode has no Low: Low uses Instant.")

    def _choose_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "The resume_agent folder", self.maker.agent_dir or "")
        if folder:
            config.agent_dir = folder
            self._show()

    def _show_problem(self, text: str) -> None:
        self.problem.setText(text)
        self.problem.show()

    def _add_line(self, stamp: str, level: str, text: str) -> None:
        prefix = {"WARN": "⚠ ", "ERROR": "✕ "}.get(level, "")
        self.log.appendPlainText(f"{stamp}  {prefix}{text}")
        self.log.moveCursor(QTextCursor.End)

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.log.toPlainText())

