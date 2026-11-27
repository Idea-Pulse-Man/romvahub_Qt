"""The Start window: what this computer's Resume Maker does when Start resume is clicked.

One Profile, ▲ Up or ▼ Down and the No. to start from, the method (one step, or two steps with
DeepSeek first), the Resume's AI, the cover letter's own AI, and each AI's choices. The choices are
kept on this computer (config) and sent to the server for this computer (`maker_computers`), whose
queue then hands out that Profile's applications in that order — so several computers can work on
one Profile from different points without making the same Resume twice.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget,
)

from ..config import AI_SITES, CHATGPT_EFFORTS, CHATGPT_MODELS, CHATGPT_MODES, CLAUDE_MODELS, config
from ..state import ALL, AppState
from .widgets import Segmented, label

NAMES = {key: name for key, name, _site in AI_SITES}
# Two steps: DeepSeek always writes the draft; the Resume is then written by one of these.
SECOND_STEP = ("chatgpt", "claude", "gemini")


class StartWindow(QDialog):
    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Start resume")
        self.setMinimumWidth(520)
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

        # Method and AIs.
        self.method = Segmented([("one", "One step"), ("two", "Two steps (DeepSeek first)")], config.maker_method)
        form.addRow("Method", self.method)
        self.ai = QComboBox()
        form.addRow("Resume AI", self.ai)
        self.letter_ai = QComboBox()
        for key, name, _site in AI_SITES:
            self.letter_ai.addItem(name, key)
        self.letter_ai.setCurrentIndex(max(0, self.letter_ai.findData(config.maker_letter_ai)))
        form.addRow("Cover letter AI", self.letter_ai)

        # ChatGPT's mode, model and effort; DeepSeek's switches.
        self.chatgpt_box = QWidget()
        gpt = QHBoxLayout(self.chatgpt_box)
        gpt.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        for key, name in CHATGPT_MODES:
            self.mode.addItem(name, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.chatgpt_mode)))
        self.model = QComboBox()
        self.model.setEditable(True)
        self.effort = QComboBox()
        for key, name in CHATGPT_EFFORTS:
            self.effort.addItem(name, key)
        self.effort.setCurrentIndex(max(0, self.effort.findData(config.chatgpt_effort)))
        gpt.addWidget(self.mode)
        gpt.addWidget(self.model, 1)
        gpt.addWidget(self.effort)
        form.addRow("ChatGPT", self.chatgpt_box)
        self.deepseek_box = QWidget()
        ds = QHBoxLayout(self.deepseek_box)
        ds.setContentsMargins(0, 0, 0, 0)
        self.deepthink = QCheckBox("DeepThink")
        self.deepthink.setChecked(config.deepseek_deepthink)
        self.search = QCheckBox("Search")
        self.search.setChecked(config.deepseek_search)
        ds.addWidget(self.deepthink)
        ds.addWidget(self.search)
        ds.addStretch(1)
        form.addRow("DeepSeek", self.deepseek_box)
        # Claude's model and Extended thinking (Romva Apply sets them in claude.ai); Gemini: its own default.
        self.claude_box = QWidget()
        cl = QHBoxLayout(self.claude_box)
        cl.setContentsMargins(0, 0, 0, 0)
        self.claude_model = QComboBox()
        self.claude_model.setEditable(True)
        self.claude_model.addItems(list(CLAUDE_MODELS))
        self.claude_model.setCurrentText(config.claude_model)
        self.claude_model.setToolTip("The model as Claude's model menu names it. Another name can be typed in.")
        self.claude_thinking = QCheckBox("Extended thinking")
        self.claude_thinking.setChecked(config.claude_thinking)
        cl.addWidget(self.claude_model, 1)
        cl.addWidget(self.claude_thinking)
        form.addRow("Claude", self.claude_box)
        self.gemini_note = label("Uses the model set on gemini.google.com (no model choice yet).", "Muted", wrap=True)
        form.addRow("Gemini", self.gemini_note)
        self.form = form
        lay.addLayout(form)

        self.error = label("", "Error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Start")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.method.changed.connect(lambda _key: self._fill_ais())
        self.ai.currentIndexChanged.connect(lambda _i: self._show_options())
        self.letter_ai.currentIndexChanged.connect(lambda _i: self._show_options())
        self.mode.currentIndexChanged.connect(lambda _i: self._fill_models())
        self.order.changed.connect(lambda _key: self._note())
        self._fill_ais()
        self._fill_models()
        self._note()

    # ------------------------------------------------------------------ helpers
    def _method(self) -> str:
        return self.method.current or config.maker_method

    def _fill_ais(self) -> None:
        keep = self.ai.currentData() or config.maker_ai
        self.ai.blockSignals(True)
        self.ai.clear()
        for key, name, _site in AI_SITES:
            if self._method() == "two" and key not in SECOND_STEP:
                continue
            self.ai.addItem(name, key)
        index = self.ai.findData(keep)
        self.ai.setCurrentIndex(index if index >= 0 else 0)
        self.ai.blockSignals(False)
        self._show_options()

    def _fill_models(self) -> None:
        mode = self.mode.currentData() or "chat"
        self.model.clear()
        self.model.addItems(list(CHATGPT_MODELS.get(mode, CHATGPT_MODELS["chat"])))
        self.model.setCurrentText(config.chatgpt_model(mode))

    def _used(self) -> set[str]:
        used = {self.ai.currentData(), self.letter_ai.currentData()}
        if self._method() == "two":
            used.add("deepseek")
        return used

    def _used_for(self, site: str) -> str:
        """What an AI writes here: "the draft", "the Resume and the cover letter"…"""
        parts = (["the draft"] if self._method() == "two" and site == "deepseek" else []) + \
                (["the Resume"] if self.ai.currentData() == site else []) + \
                (["the cover letter"] if self.letter_ai.currentData() == site else [])
        return f"{', '.join(parts[:-1])} and {parts[-1]}" if len(parts) > 1 else (parts[0] if parts else "")

    def _show_options(self) -> None:
        """Only the AIs in use, each saying what it writes (a ChatGPT row kept for the letter is not the Resume's)."""
        used = self._used()
        for site, name, widget in (("chatgpt", "ChatGPT", self.chatgpt_box), ("claude", "Claude", self.claude_box),
                                   ("gemini", "Gemini", self.gemini_note), ("deepseek", "DeepSeek", self.deepseek_box)):
            self.form.setRowVisible(widget, site in used)
            row_label = self.form.labelForField(widget)
            if site in used and row_label is not None:
                row_label.setText(f"{name}<br><span style='color:#9AA3B2; font-size:11px'>for {self._used_for(site)}</span>")
        self.adjustSize()

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
        # Kept on this computer: the Resume Maker page shows the same choices, and the agent gets them at start.
        config.start_profile = self.profile.currentData()
        config.start_order = (self.order.current or "up")
        config.maker_method = self._method()
        config.maker_ai = self.ai.currentData()
        config.maker_draft_ai = "deepseek"
        config.maker_letter_ai = self.letter_ai.currentData()
        mode = self.mode.currentData() or "chat"
        config.chatgpt_mode = mode
        config.set_chatgpt_model(mode, self.model.currentText())
        config.chatgpt_effort = self.effort.currentData() or "high"
        config.deepseek_deepthink = self.deepthink.isChecked()
        config.deepseek_search = self.search.isChecked()
        config.claude_model = self.claude_model.currentText() or CLAUDE_MODELS[0]
        config.claude_thinking = self.claude_thinking.isChecked()
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
                "method": config.maker_method,
                "ai": config.maker_ai,
                **({"draftAi": "deepseek"} if config.maker_method == "two" else {}),
                "letterAi": config.maker_letter_ai,
                "models": config.maker_models(),
            },
        }
