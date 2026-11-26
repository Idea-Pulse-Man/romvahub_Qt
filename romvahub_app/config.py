"""The app's settings, per Windows user (QSettings: the registry under HKCU\\Software\\Romva\\RomvaHub).

Nothing secret is kept here: the sign-in and the Profile tokens live in Windows
Credential Manager (vault.py). This holds choices (theme, rows per page, the
connection method) and the non-secret details of each token (its Profile's
name, a masked form, when it expires) so the app can list them.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

from . import APP_ID, ORG_NAME

DEFAULT_SERVER = "https://www.romva.space"
PAGE_SIZES = (5, 10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 5
AI_SITES = (("chatgpt", "ChatGPT", "chatgpt.com"), ("deepseek", "DeepSeek", "chat.deepseek.com"),
            ("claude", "Claude", "claude.ai"), ("gemini", "Gemini", "gemini.google.com"))
# How a resume is made: one prompt (one AI), or two (the first AI writes a draft, the second the resume from it).
MAKER_METHODS = (("one", "One prompt"), ("two", "Two prompts"))
# ChatGPT's Chat / Work mode, the models its model menu lists in each (2026-11-26; any other name can be
# typed), and the thinking effort. The Resume agent chooses them in every chat (resume_agent chat.js).
CHATGPT_MODES = (("chat", "Chat"), ("work", "Work"))
CHATGPT_MODELS = {
    "chat": ("GPT-6", "GPT-6.2", "GPT-5.6 Sol"),
    "work": ("GPT-6 Sol", "GPT-6.2 Sol", "GPT-6.2 Astra", "GPT-6.1 Sol", "GPT-6.1 Terra", "GPT-6 Astra", "GPT-6 Luna",
             "GPT-5.6 Sol", "GPT-5.6 Terra", "GPT-5.6 Luna", "Default"),
}
CHATGPT_EFFORTS = (("low", "Low"), ("medium", "Medium"), ("high", "High"))


def _settings() -> QSettings:
    return QSettings(ORG_NAME, APP_ID)


def _get(key: str, default):
    value = _settings().value(key, default)
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes")
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _set(key: str, value) -> None:
    s = _settings()
    s.setValue(key, value)
    s.sync()


class Config:
    """Typed access to the saved settings."""

    # The server (romva.space, or the VPS's address).
    @property
    def server_url(self) -> str:
        return str(_get("server_url", DEFAULT_SERVER)).rstrip("/") or DEFAULT_SERVER

    @server_url.setter
    def server_url(self, value: str) -> None:
        _set("server_url", value.strip().rstrip("/") or DEFAULT_SERVER)

    # "account" (email and password) or "token" (Profile tokens).
    @property
    def method(self) -> str:
        value = str(_get("method", "account"))
        return value if value in ("account", "token") else "account"

    @method.setter
    def method(self, value: str) -> None:
        _set("method", value)

    @property
    def last_email(self) -> str:
        return str(_get("last_email", ""))

    @last_email.setter
    def last_email(self, value: str) -> None:
        _set("last_email", value)

    @property
    def keep_signed_in(self) -> bool:
        return _get("keep_signed_in", True)

    @keep_signed_in.setter
    def keep_signed_in(self, value: bool) -> None:
        _set("keep_signed_in", bool(value))

    # The Applications table.
    @property
    def page_size(self) -> int:
        value = _get("page_size", DEFAULT_PAGE_SIZE)
        return value if value in PAGE_SIZES else DEFAULT_PAGE_SIZE

    @page_size.setter
    def page_size(self, value: int) -> None:
        _set("page_size", int(value))

    # "light", "dark" or "system".
    @property
    def theme(self) -> str:
        value = str(_get("theme", "light"))
        return value if value in ("light", "dark", "system") else "light"

    @theme.setter
    def theme(self, value: str) -> None:
        _set("theme", value)

    @property
    def chrome_path(self) -> str:
        return str(_get("chrome_path", ""))

    @chrome_path.setter
    def chrome_path(self, value: str) -> None:
        _set("chrome_path", value)

    # The Resume Maker.
    @property
    def agent_dir(self) -> str:
        # The built-in agent always wins; a chosen folder only counts while it still holds the agent.
        if bundled := bundled_agent_dir():
            return bundled
        saved = str(_get("agent_dir", ""))
        return saved if saved and _is_agent(Path(saved)) else default_agent_dir()

    @agent_dir.setter
    def agent_dir(self, value: str) -> None:
        _set("agent_dir", value)

    # The Resume Maker: the method, and the AI for each part (keys of AI_SITES).
    @property
    def maker_method(self) -> str:
        value = str(_get("maker_method", "two"))
        return value if value in [m[0] for m in MAKER_METHODS] else "two"

    @maker_method.setter
    def maker_method(self, value: str) -> None:
        _set("maker_method", value)

    def _ai(self, key: str, default: str) -> str:
        value = str(_get(key, default))
        return value if value in [a[0] for a in AI_SITES] else default

    @property
    def maker_ai(self) -> str:
        """The AI that writes the resume: the only one (one prompt), or the second (two prompts)."""
        return self._ai("maker_ai", "chatgpt")

    @maker_ai.setter
    def maker_ai(self, value: str) -> None:
        _set("maker_ai", value)

    @property
    def maker_draft_ai(self) -> str:
        """The first of two prompts: writes the draft."""
        return self._ai("maker_draft_ai", "deepseek")

    @maker_draft_ai.setter
    def maker_draft_ai(self, value: str) -> None:
        _set("maker_draft_ai", value)

    @property
    def maker_letter_ai(self) -> str:
        """The AI that writes the cover letter (one prompt)."""
        return self._ai("maker_letter_ai", "chatgpt")

    @maker_letter_ai.setter
    def maker_letter_ai(self, value: str) -> None:
        _set("maker_letter_ai", value)

    def maker_ais_used(self) -> set[str]:
        """Every AI the Resume Maker asks, as chosen now."""
        used = {self.maker_ai, self.maker_letter_ai}
        if self.maker_method == "two":
            used.add(self.maker_draft_ai)
        return used

    # DeepSeek has no model menu: its DeepThink and Search switches.
    @property
    def deepseek_deepthink(self) -> bool:
        return _get("deepseek_deepthink", True)

    @deepseek_deepthink.setter
    def deepseek_deepthink(self, value: bool) -> None:
        _set("deepseek_deepthink", bool(value))

    @property
    def deepseek_search(self) -> bool:
        return _get("deepseek_search", True)

    @deepseek_search.setter
    def deepseek_search(self, value: bool) -> None:
        _set("deepseek_search", bool(value))

    def maker_models(self) -> dict:
        """Each AI's own choices, for the Resume agent (its config.json "models")."""
        mode = self.chatgpt_mode
        return {
            "chatgpt": {"mode": mode, "model": self.chatgpt_model(mode), "effort": self.chatgpt_effort},
            "deepseek": {"deepThink": self.deepseek_deepthink, "search": self.deepseek_search},
        }

    # ChatGPT's mode, model (one per mode: the two list different models) and thinking effort.
    @property
    def chatgpt_mode(self) -> str:
        value = str(_get("chatgpt_mode", "chat"))
        return value if value in CHATGPT_MODELS else "chat"

    @chatgpt_mode.setter
    def chatgpt_mode(self, value: str) -> None:
        _set("chatgpt_mode", value)

    def chatgpt_model(self, mode: str) -> str:
        return str(_get(f"chatgpt_model_{mode}", CHATGPT_MODELS.get(mode, CHATGPT_MODELS["chat"])[0])).strip()

    def set_chatgpt_model(self, mode: str, value: str) -> None:
        _set(f"chatgpt_model_{mode}", value.strip())

    @property
    def chatgpt_effort(self) -> str:
        value = str(_get("chatgpt_effort", "high"))
        return value if value in [e[0] for e in CHATGPT_EFFORTS] else "high"

    @chatgpt_effort.setter
    def chatgpt_effort(self, value: str) -> None:
        _set("chatgpt_effort", value)

    @property
    def maker_autostart(self) -> bool:
        return _get("maker_autostart", False)

    @maker_autostart.setter
    def maker_autostart(self, value: bool) -> None:
        _set("maker_autostart", bool(value))

    @property
    def notify_ready(self) -> bool:
        return _get("notify_ready", True)

    @notify_ready.setter
    def notify_ready(self, value: bool) -> None:
        _set("notify_ready", bool(value))

    @property
    def start_with_windows(self) -> bool:
        return _get("start_with_windows", False)

    @start_with_windows.setter
    def start_with_windows(self, value: bool) -> None:
        _set("start_with_windows", bool(value))
        set_run_at_login(bool(value))

    # Non-secret details of the Profile tokens added in token mode, per server:
    # [{ "profileId", "profileName", "mask", "label", "expiresAt", "revoked" }].
    def token_entries(self, server: str) -> list[dict]:
        raw = _get(f"tokens/{_key(server)}", "[]")
        try:
            entries = json.loads(raw) if isinstance(raw, str) else []
        except ValueError:
            entries = []
        return [e for e in entries if isinstance(e, dict) and e.get("profileId")]

    def set_token_entries(self, server: str, entries: list[dict]) -> None:
        _set(f"tokens/{_key(server)}", json.dumps(entries))

    @property
    def last_profile(self) -> str:
        return str(_get("last_profile", ""))

    @last_profile.setter
    def last_profile(self, value: str) -> None:
        _set("last_profile", value)


def _key(server: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in server.lower())


def app_dir() -> Path:
    """The folder the app runs from (the source folder, or the frozen .exe's folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _is_agent(folder: Path) -> bool:
    return (folder / "src" / "agent.js").exists()


def bundled_agent_dir() -> str:
    """The Resume agent built into the app (build.ps1): <app>\\agent, with its own node.exe and node_modules."""
    folder = app_dir() / "agent"
    return str(folder) if _is_agent(folder) and (folder / "node.exe").exists() else ""


def default_agent_dir() -> str:
    """The Resume agent's folder: built in, or next to the app (the repo layout)."""
    if bundled := bundled_agent_dir():
        return bundled
    for candidate in (app_dir() / "resume_agent", app_dir().parent / "resume_agent"):
        if _is_agent(candidate):
            return str(candidate)
    return ""


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def set_run_at_login(enabled: bool) -> None:
    """Start with Windows: the HKCU Run key, pointing at this app."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}" --minimized'
                else:
                    pythonw = Path(sys.executable).with_name("pythonw.exe")
                    exe = pythonw if pythonw.exists() else Path(sys.executable)
                    command = f'"{exe}" "{app_dir() / "main.py"}" --minimized'
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_ID)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except OSError:
        pass


config = Config()
