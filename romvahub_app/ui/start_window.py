"""The Start window: what this computer's Resume Maker does when Start resume is clicked.

One Profile, ▲ Up or ▼ Down and the No. to start from, the Method, and a table of lines: each its own AI with
that AI's own settings on the same line.

- **One step:** the Resume (the Profile's Resume prompt) and the cover letter.
- **Two steps** (Romva Apply in the app's Chrome only): Step 1 (the information the Resume needs: company,
  role, experience, with the Profile's Step 1 prompt), Step 2 (the Resume from it, with the Step 2 prompt) and
  the cover letter.

Start is blocked, saying what is missing, while the Profile has no prompts for the Method (romva.space refuses
it too). The choices are kept on this computer (config) and sent to the server for this computer
(`maker_computers`), whose queue then hands out that Profile's applications in that order — so several
computers can work on one Profile from different points without making the same Resume twice.
"""

from __future__ import annotations

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import tasks
from ..config import AI_SITES, CHATGPT_EFFORTS, CHATGPT_MODELS, CHATGPT_MODES, CLAUDE_MODELS, config
from ..state import ALL, AppState
from .widgets import Segmented, label

SITES = [key for key, _name, _site in AI_SITES]
METHODS = [("one", "One step"), ("two", "Two steps")]


def _site_settings(site: str) -> dict:
    """An AI's settings as this computer last had them (the Resume Maker page and the old Start window)."""
    if site == "chatgpt":
        mode = config.chatgpt_mode
        return {"mode": mode, "model": config.chatgpt_model(mode), "effort": config.chatgpt_effort}
    if site == "claude":
        return {"model": config.claude_model, "thinking": config.claude_thinking}
    if site == "deepseek":
        return {"deepThink": config.deepseek_deepthink, "search": config.deepseek_search}
    return {}


def _row(*widgets, stretch_last: bool = False) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for widget in widgets:
        lay.addWidget(widget)
    if not stretch_last:
        lay.addStretch(1)
    return box


def missing_prompts(prompts: dict, method: str) -> list[str]:
    """What a Profile lacks for `method` (its prompts, its own template), from /api/profiles/:id/prompts."""
    def filled(key: str) -> bool:
        return bool(str(prompts.get(key) or "").strip())

    if method == "two":
        needs = [name for key, name in (("resumeStep1Prompt", "Step 1 prompt"), ("resumeStep2Prompt", "Step 2 prompt"))
                 if not filled(key)]
    else:
        needs = [] if filled("resumePrompt") else ["Resume prompt"]
    return needs + ([] if prompts.get("hasOwnTemplate", True) else ["Resume template"])


class PartLine:
    """One line of the table: the part's AI, and that AI's own settings beside it."""

    def __init__(self, grid: QGridLayout, row: int, title: str, saved: dict, fallback_site: str):
        site = saved.get("site") if saved.get("site") in SITES else fallback_site
        settings = {key: {**_site_settings(key), **(saved.get(key) or {})} for key in SITES}

        self.ai = QComboBox()
        for key, name, _site in AI_SITES:
            self.ai.addItem(name, key)
        self.ai.setCurrentIndex(max(0, self.ai.findData(site)))
        self.ai.setMinimumWidth(120)

        # ChatGPT: Chat / Work, the model and the thinking effort.
        gpt = settings["chatgpt"]
        self.mode = QComboBox()
        for key, name in CHATGPT_MODES:
            self.mode.addItem(name, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(gpt.get("mode", "chat"))))
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(130)
        self.model.setToolTip("The model as ChatGPT's model menu names it. Another name can be typed in.")
        self.effort = QComboBox()
        for key, name in CHATGPT_EFFORTS:
            self.effort.addItem(name, key)
        self.effort.setCurrentIndex(max(0, self.effort.findData(gpt.get("effort", "high"))))
        self._fill_models(str(gpt.get("model") or ""))
        self.mode.currentIndexChanged.connect(lambda _i: self._fill_models(""))

        # Claude: the model and Extended thinking.
        claude = settings["claude"]
        self.claude_model = QComboBox()
        self.claude_model.setEditable(True)
        self.claude_model.setMinimumWidth(130)
        self.claude_model.addItems(list(CLAUDE_MODELS))
        self.claude_model.setCurrentText(str(claude.get("model") or CLAUDE_MODELS[0]))
        self.claude_model.setToolTip("The model as Claude's model menu names it. Another name can be typed in.")
        self.thinking = QCheckBox("Extended thinking")
        self.thinking.setChecked(claude.get("thinking", True) is not False)

        # DeepSeek: no model menu, its two switches.
        deepseek = settings["deepseek"]
        self.deepthink = QCheckBox("DeepThink")
        self.deepthink.setChecked(deepseek.get("deepThink", True) is not False)
        self.search = QCheckBox("Search")
        self.search.setChecked(deepseek.get("search", True) is not False)

        self.stack = QStackedWidget()
        self.pages = {
            "chatgpt": self.stack.addWidget(_row(self.mode, self.model, self.effort)),
            "claude": self.stack.addWidget(_row(self.claude_model, self.thinking)),
            "deepseek": self.stack.addWidget(_row(self.deepthink, self.search)),
            "gemini": self.stack.addWidget(_row(label("Gemini's own default model", "Muted"))),
        }
        self.ai.currentIndexChanged.connect(lambda _i: self.stack.setCurrentIndex(self.pages[self.site()]))
        self.stack.setCurrentIndex(self.pages[self.site()])

        self.title = label(title)
        grid.addWidget(self.title, row, 0)
        grid.addWidget(self.ai, row, 1)
        grid.addWidget(self.stack, row, 2)

    def set_shown(self, shown: bool) -> None:
        for widget in (self.title, self.ai, self.stack):
            widget.setVisible(shown)

    def _fill_models(self, wanted: str) -> None:
        names = list(CHATGPT_MODELS.get(self.mode.currentData() or "chat", CHATGPT_MODELS["chat"]))
        self.model.clear()
        self.model.addItems(names)
        self.model.setCurrentText(wanted or names[0])

    def site(self) -> str:
        return self.ai.currentData() or "chatgpt"

    def settings(self, site: str | None = None) -> dict:
        """The settings this line asks its AI with (the server's choices.parts)."""
        site = site or self.site()
        if site == "chatgpt":
            return {"mode": self.mode.currentData() or "chat", "model": self.model.currentText().strip(),
                    "effort": self.effort.currentData() or "high"}
        if site == "claude":
            return {"model": self.claude_model.currentText().strip() or CLAUDE_MODELS[0],
                    "thinking": self.thinking.isChecked()}
        if site == "deepseek":
            return {"deepThink": self.deepthink.isChecked(), "search": self.search.isChecked()}
        return {}

    def saved(self) -> dict:
        """What this computer keeps for the line: its AI, and every AI's settings as set here."""
        return {"site": self.site(), **{key: self.settings(key) for key in SITES}}


class StartWindow(QDialog):
    def __init__(self, state: AppState, parent: QWidget | None = None, token_profile_id: str | None = None,
                 stop_note: str = ""):
        """`token_profile_id`: the Profile of the token in this computer's Romva Apply, when the server knows it —
        the only one offered (it is the only one that computer can make Resumes for). `stop_note`: why romva.space
        stopped this computer (its Profile had no prompts for the Method), shown at the top."""
        super().__init__(parent)
        self.state = state
        # Two steps are made by romva.space's engine, in the app's Chrome with Romva Apply.
        self.browser = config.maker_engine == "browser"
        self.prompts: dict | None = None  # the chosen Profile's, once read
        self.setWindowTitle("Start resume")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        if stop_note:
            lay.addWidget(label(f"Stopped by romva.space: {stop_note}", "Error", wrap=True))
        lay.addWidget(label("What this computer makes, and how. Several computers can work on one Profile: give "
                            "each its own start No. — no Resume is made twice.", "Muted", wrap=True))
        form = QFormLayout()
        form.setVerticalSpacing(10)

        # Profile: one — the token's in Romva Apply when known, and only if this account may use it.
        self.profile = QComboBox()
        self.token_problem = ""
        mine = [p for p in state.profiles if not p.get("revoked")]
        if token_profile_id:
            match = next((p for p in mine if p.get("id") == token_profile_id), None)
            if match:
                self.profile.addItem(f"{match.get('name') or 'Profile'}  (the Profile of the token in Romva Apply)",
                                     match.get("id"))
            else:
                self.token_problem = ("The token in Romva Apply in the app's Chrome is for a Profile your account can't "
                                      "use. Paste the token of one of your Profiles in Romva Apply.")
            self.profile.setEnabled(False)
        else:
            for p in mine:
                self.profile.addItem(p.get("name") or "Profile", p.get("id"))
            wanted = config.start_profile or (state.profile_id if state.profile_id != ALL else None)
            index = self.profile.findData(wanted) if wanted else -1
            if index >= 0:
                self.profile.setCurrentIndex(index)
        form.addRow("Profile", self.profile)

        # Order and start No.
        order_row = QHBoxLayout()
        self.order = Segmented([("up", "▲ Up"), ("down", "▼ Down")], config.start_order)
        order_row.addWidget(self.order)
        order_row.addSpacing(16)
        order_row.addWidget(label("Start from No."))
        self.start_from = QLineEdit()
        self.start_from.setValidator(QIntValidator(1, 10_000_000, self))
        self.start_from.setPlaceholderText("first / last")
        self.start_from.setMaximumWidth(110)
        order_row.addWidget(self.start_from)
        order_row.addStretch(1)
        form.addRow("Order", order_row)
        self.order_note = label("", "Muted", wrap=True)
        form.addRow("", self.order_note)

        # The Method: one step, or two (Step 1: the information; Step 2: the Resume).
        method_row = QHBoxLayout()
        self.method = Segmented(METHODS, config.maker_method if self.browser else "one")
        self.method.setEnabled(self.browser)
        method_row.addWidget(self.method)
        method_row.addStretch(1)
        form.addRow("Method", method_row)
        self.method_note = label("", "Muted", wrap=True)
        form.addRow("", self.method_note)
        lay.addLayout(form)

        # The table: (Step 1,) the Resume and the cover letter, each its AI and that AI's settings.
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(2, 1)
        grid.addWidget(label("AI", "Muted"), 0, 1)
        grid.addWidget(label("Settings", "Muted"), 0, 2)
        parts = config.start_parts
        self.draft = PartLine(grid, 1, "Step 1 · information", parts.get("draft") or {}, config.maker_draft_ai)
        self.resume = PartLine(grid, 2, "Resume", parts.get("resume") or {}, config.maker_ai)
        self.letter = PartLine(grid, 3, "Cover letter", parts.get("letter") or {}, config.maker_letter_ai)
        lay.addLayout(grid)

        self.error = label("", "Error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.ok.setText("Start")
        self.ok.setObjectName("Primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.order.changed.connect(lambda _key: self._note())
        self.method.changed.connect(lambda _key: self._show_method())
        self.profile.currentIndexChanged.connect(lambda _i: self._load_prompts())
        self._note()
        self._show_method()
        self._load_prompts()

    # ------------------------------------------------------------------ helpers
    def _method(self) -> str:
        return (self.method.current or "one") if self.browser else "one"

    def _note(self) -> None:
        down = (self.order.current or "up") == "down"
        self.order_note.setText("From the start No. down (900, 899, 898…); empty: from the highest. Past the end it "
                                "carries on with what is left." if down else
                                "From the start No. up (450, 451, 452…); empty: from the lowest not made yet. Past "
                                "the end it carries on with what is left.")

    def _show_method(self) -> None:
        two = self._method() == "two"
        self.draft.set_shown(two)
        self.resume.title.setText("Step 2 · Resume" if two else "Resume")
        if not self.browser:
            text = ("One step: the Resume agent in this app. Two steps run in the app's Chrome with Romva Apply "
                    "(Settings → Resume Maker runs in → Chrome + Romva Apply).")
        elif two:
            text = ("Step 1's AI writes the information the Resume needs (company, role, experience); Step 2's AI "
                    "writes the Resume from it. Each step uses its own prompt from the Profile.")
        else:
            text = "One AI writes the Resume with the Profile's Resume prompt."
        self.method_note.setText(text)
        self._check()

    def _load_prompts(self) -> None:
        """The chosen Profile's prompts, to block Start while it has none for the Method."""
        self.prompts = None
        profile_id = self.profile.currentData()
        self._check()
        if not profile_id:
            return

        def loaded(data, wanted=profile_id) -> None:
            if wanted == self.profile.currentData():
                self.prompts = data if isinstance(data, dict) else {}
                self._check()

        def failed(_error, wanted=profile_id) -> None:
            # Not readable here: romva.space still checks at Start.
            if wanted == self.profile.currentData():
                self.prompts = {}
                self._check()

        tasks.run(lambda: self.state.api.prompts(profile_id), loaded, failed, owner=self)

    def _check(self) -> None:
        """Start only with a Profile that can make Resumes with the Method; else what is missing."""
        problem = self.token_problem
        if not problem and self.prompts:
            missing = missing_prompts(self.prompts, self._method())
            if missing:
                problem = (f"This Profile has no {' or '.join(missing)} for Two steps. Add them in Profiles → Prompts & "
                           "Template, or choose One step." if self._method() == "two" else
                           f"This Profile has no {' or '.join(missing)} yet. Add it in Profiles → Prompts & Template.")
        self.error.setText(problem)
        self.error.setVisible(bool(problem))
        # Not read yet: Start waits for it (a moment).
        self.ok.setEnabled(not problem and (self.prompts is not None or self.profile.currentData() is None))

    def _accept(self) -> None:
        if self.profile.currentData() is None:
            self.error.setText("Choose the Profile.")
            self.error.show()
            return
        two = self._method() == "two"
        # Kept on this computer: the next Start window, the Resume Maker page and the agent read them.
        config.start_profile = self.profile.currentData()
        config.start_order = (self.order.current or "up")
        config.start_parts = {"draft": self.draft.saved(), "resume": self.resume.saved(), "letter": self.letter.saved()}
        config.maker_method = self._method()
        config.maker_ai = self.resume.site()
        config.maker_draft_ai = self.draft.site()
        config.maker_letter_ai = self.letter.site()
        # Each AI's settings for what knows one set per AI (the Resume agent): the Resume's win.
        for line in ((self.draft,) if two else ()) + (self.letter, self.resume):
            settings = line.settings()
            if line.site() == "chatgpt":
                config.chatgpt_mode = settings["mode"]
                config.set_chatgpt_model(settings["mode"], settings["model"])
                config.chatgpt_effort = settings["effort"]
            elif line.site() == "claude":
                config.claude_model = settings["model"]
                config.claude_thinking = settings["thinking"]
            elif line.site() == "deepseek":
                config.deepseek_deepthink = settings["deepThink"]
                config.deepseek_search = settings["search"]
        self.accept()

    def choice(self) -> dict:
        """What the server keeps for this computer (PUT /api/auto-make/computers/:worker)."""
        text = self.start_from.text().strip()
        return {
            "running": True,
            "profileId": self.profile.currentData(),
            "order": (self.order.current or "up"),
            "startFrom": int(text) if text.isdigit() else None,
            "choices": {
                "method": self._method(),
                "ai": self.resume.site(),
                "draftAi": self.draft.site(),
                "letterAi": self.letter.site(),
                "models": config.maker_models(),
                "parts": {"draft": self.draft.settings(), "resume": self.resume.settings(),
                          "letter": self.letter.settings()},
            },
        }
