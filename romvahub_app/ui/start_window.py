"""The Start window: what this computer's Resume Maker does when Start resume is clicked.

One Profile, ▲ Up or ▼ Down and the No. to start from, and a two-line table: the Resume and the
cover letter, each its own AI with that AI's own settings on the same line (one step: no draft
first). The choices are kept on this computer (config) and sent to the server for this computer
(`maker_computers`), whose queue then hands out that Profile's applications in that order — so
several computers can work on one Profile from different points without making the same Resume
twice.
"""

from __future__ import annotations

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import AI_SITES, CHATGPT_EFFORTS, CHATGPT_MODELS, CHATGPT_MODES, CLAUDE_MODELS, config
from ..state import ALL, AppState
from .widgets import Segmented, label

SITES = [key for key, _name, _site in AI_SITES]


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

        grid.addWidget(label(title), row, 0)
        grid.addWidget(self.ai, row, 1)
        grid.addWidget(self.stack, row, 2)

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
    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Start resume")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(label("What this computer makes, and how. Several computers can work on one Profile: give "
                            "each its own start No. — no Resume is made twice.", "Muted", wrap=True))
        form = QFormLayout()
        form.setVerticalSpacing(10)

        # Profile: one.
        self.profile = QComboBox()
        for p in state.profiles:
            if not p.get("revoked"):
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
        lay.addLayout(form)

        # The table: Resume and cover letter, each its AI and that AI's settings.
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(2, 1)
        grid.addWidget(label("AI", "Muted"), 0, 1)
        grid.addWidget(label("Settings", "Muted"), 0, 2)
        parts = config.start_parts
        self.resume = PartLine(grid, 1, "Resume", parts.get("resume") or {}, config.maker_ai)
        self.letter = PartLine(grid, 2, "Cover letter", parts.get("letter") or {}, config.maker_letter_ai)
        lay.addLayout(grid)

        self.error = label("", "Error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Start")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.order.changed.connect(lambda _key: self._note())
        self._note()

    # ------------------------------------------------------------------ helpers
    def _note(self) -> None:
        down = (self.order.current or "up") == "down"
        self.order_note.setText("From the start No. down (900, 899, 898…); empty: from the highest. Past the end it "
                                "carries on with what is left." if down else
                                "From the start No. up (450, 451, 452…); empty: from the lowest not made yet. Past "
                                "the end it carries on with what is left.")

    def _accept(self) -> None:
        if self.profile.currentData() is None:
            self.error.setText("Choose the Profile.")
            self.error.show()
            return
        # Kept on this computer: the next Start window, the Resume Maker page and the agent read them.
        config.start_profile = self.profile.currentData()
        config.start_order = (self.order.current or "up")
        config.start_parts = {"resume": self.resume.saved(), "letter": self.letter.saved()}
        config.maker_method = "one"
        config.maker_ai = self.resume.site()
        config.maker_draft_ai = "deepseek"
        config.maker_letter_ai = self.letter.site()
        # Each AI's settings for what knows one set per AI (the Resume agent): the Resume's win.
        for line in (self.letter, self.resume):
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
                "method": "one",
                "ai": self.resume.site(),
                "letterAi": self.letter.site(),
                "models": config.maker_models(),
                "parts": {"resume": self.resume.settings(), "letter": self.letter.settings()},
            },
        }
