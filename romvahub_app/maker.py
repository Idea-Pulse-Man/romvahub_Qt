"""The Resume Maker: runs the Resume agent (resume_agent, Node.js) as a child process.

The agent makes the Resume and cover letter for each new Draft with the
bidder's own signed-in ChatGPT, Claude or Gemini (in its own Chrome window).
This app starts and stops it, hands it the sign-in, and reads its log:

* Token mode — the agent runs as the chosen Profile's token.
* Account mode — it runs with the app's 15-minute access token, and the app
  sends it a fresh one on stdin as it renews (ROMVA_TOKEN_STDIN).
"""

from __future__ import annotations

import logging
import re
import shutil
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import tasks
from .config import config, data_dir

_log = logging.getLogger("romvahub.maker")
LINE = re.compile(r"^(\S+)\s+(INFO|WARN|ERROR)\s+(.*)$")
MAKING = re.compile(r"^Making #(\S+) (.+?) — (.+)$")
MAKING_LETTER = re.compile(r"^Making the cover letter for #(\S+) (.+?) — (.+)$")


@dataclass
class CurrentJob:
    number: str
    company: str
    role: str
    step: int = 1  # 1 read, 2 resume, 3 cover letter, 4 files, 5 saved
    letter_only: bool = False


def node_path() -> str:
    found = shutil.which("node")
    if found:
        return found
    for candidate in (r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"):
        if Path(candidate).exists():
            return candidate
    return ""


def npm_path() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or ""


class Maker(QObject):
    state_changed = Signal(bool)  # running
    line = Signal(str, str, str)  # time, level, text
    job_changed = Signal(object)  # CurrentJob | None
    made = Signal(str)  # company: a Resume (and letter) is done
    problem = Signal(str)  # a message for the bidder (no Node, no agent, ...)

    def __init__(self, api_provider, parent=None):
        super().__init__(parent)
        self._api_provider = api_provider  # () -> Api | None
        self.proc: QProcess | None = None
        self.installer: QProcess | None = None
        self.job: CurrentJob | None = None
        self.made_today = 0
        self.failed_today = 0
        self.profile_id: str | None = None
        self.lines: list[tuple[str, str, str]] = []
        self._renew = QTimer(self)
        self._renew.setInterval(5 * 60_000)
        self._renew.timeout.connect(self._send_fresh_token)
        self._stopping = False

    # ------------------------------------------------------------------ status
    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    @property
    def agent_dir(self) -> str:
        return config.agent_dir

    def readiness(self) -> str | None:
        """Why the maker can't start, or None."""
        if not node_path():
            return "Node.js was not found. Install it from https://nodejs.org, then restart the app."
        agent = Path(self.agent_dir) if self.agent_dir else None
        if not agent or not (agent / "src" / "agent.js").exists():
            return "The Resume agent folder was not found. Choose it in Resume Maker → Agent folder."
        if not (agent / "node_modules").exists():
            return "The Resume agent is not installed yet. Click “Install / Update”."
        return None

    # ------------------------------------------------------------------ control
    def start(self, profile_id: str | None = None) -> None:
        if self.running:
            return
        problem = self.readiness()
        if problem:
            self.problem.emit(problem)
            return
        api = self._api_provider()
        if api is None:
            self.problem.emit("Sign in first.")
            return
        self.profile_id = profile_id
        session = api.session

        def get_token():
            if session.mode == "token":
                pid = profile_id or next(iter(session.tokens), None)
                token = session.tokens.get(pid or "")
                if not token:
                    raise RuntimeError("Add a Profile token first (Settings → Connection).")
                return token
            return api.access_token()

        tasks.run(get_token, lambda token: self._launch(token, session.mode == "account"),
                  lambda error: self.problem.emit(str(getattr(error, "message", error))), owner=self)

    def _launch(self, token: str, renewable: bool) -> None:
        agent = Path(self.agent_dir)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("ROMVA_TOKEN", token)
        env.insert("ROMVA_API_URL", config.server_url)
        env.insert("ROMVA_AI", config.maker_ai)
        env.insert("ROMVA_AGENT_HOME", str(data_dir() / "agent"))
        if renewable:
            env.insert("ROMVA_TOKEN_STDIN", "1")
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(agent))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(
            lambda error: self._emit_line("ERROR", f"Could not start the agent: {proc.errorString()}")
            if error == QProcess.FailedToStart else None
        )
        self._refused = False
        self.proc = proc
        self._stopping = False
        proc.start(node_path(), [str(agent / "src" / "agent.js")])
        if renewable:
            self._renew.start()
        self._emit_line("INFO", f"Resume Maker started ({self.ai_name()})")
        self.state_changed.emit(True)

    def stop(self) -> None:
        if not self.running:
            return
        self._stopping = True
        self._renew.stop()
        assert self.proc is not None
        self.proc.kill()

    def _finished(self, code: int, _status) -> None:
        self._renew.stop()
        if self._stopping:
            self._emit_line("INFO", "Stopped by you. Anything it was making goes back to the queue.")
        elif code == 2 or getattr(self, "_refused", False):
            self.problem.emit("The server refused the Resume Maker's sign-in. Check Settings → Connection.")
            self._emit_line("ERROR", "The agent's sign-in was refused. Check Settings → Connection.")
        elif code != 0:
            self._emit_line("ERROR", f"The agent stopped (exit code {code}).")
        self.proc = None
        self._set_job(None)
        self.state_changed.emit(False)

    def _send_fresh_token(self) -> None:
        api = self._api_provider()
        if not api or not self.running:
            return

        def send(token: str) -> None:
            if self.proc is not None and self.running:
                self.proc.write(f"token {token}\n".encode())

        tasks.run(api.access_token, send, lambda e: self._emit_line("WARN", f"Could not renew the agent's sign-in: {e}"),
                  owner=self)

    # ------------------------------------------------------------------ install
    def install(self) -> None:
        npm = npm_path()
        if not npm:
            self.problem.emit("npm was not found. Install Node.js from https://nodejs.org.")
            return
        if not self.agent_dir:
            self.problem.emit("Choose the Resume agent folder first.")
            return
        proc = QProcess(self)
        proc.setWorkingDirectory(self.agent_dir)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: [self._emit_line("INFO", f"[install] {t}") for t in bytes(proc.readAllStandardOutput()).decode(errors="replace").splitlines() if t.strip()]
        )
        proc.finished.connect(lambda code, _s: self._emit_line("INFO" if code == 0 else "ERROR",
                                                                "Install finished." if code == 0 else f"Install failed (exit {code})."))
        self.installer = proc
        self._emit_line("INFO", "Installing the Resume agent (npm install)…")
        proc.start(npm, ["install", "--omit=dev"])

    # ------------------------------------------------------------------ log
    def ai_name(self) -> str:
        from .config import AI_SITES

        return next((name for key, name, _ in AI_SITES if key == config.maker_ai), "ChatGPT")

    def _read(self) -> None:
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            match = LINE.match(raw)
            if match:
                self._handle(match.group(2), match.group(3))
            else:
                self._emit_line("INFO", raw)

    def _handle(self, level: str, text: str) -> None:
        message = text.split(" {", 1)[0]
        if "token was refused" in text.lower():
            self._refused = True
        self._emit_line(level, text)
        if m := MAKING_LETTER.match(message):
            self._set_job(CurrentJob(m.group(1), m.group(2), m.group(3), step=3, letter_only=True))
        elif m := MAKING.match(message):
            self._set_job(CurrentJob(m.group(1), m.group(2), m.group(3), step=2))
        elif self.job and message.startswith("Resume") and "saved" in message:
            self.job.step = max(self.job.step, 3)
            self.job_changed.emit(self.job)
        elif self.job and message.startswith("Cover letter") and "saved" in message:
            self.job.step = 5
            self.job_changed.emit(self.job)
        elif message == "Done":
            company = self.job.company if self.job else ""
            self.made_today += 1
            self._set_job(None)
            self.made.emit(company)
        elif message.startswith("Failed:"):
            self.failed_today += 1
            self._set_job(None)

    def _set_job(self, job: CurrentJob | None) -> None:
        self.job = job
        self.job_changed.emit(job)

    def _emit_line(self, level: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        _log.log({"WARN": logging.WARNING, "ERROR": logging.ERROR}.get(level, logging.INFO), "%s", text)
        self.lines.append((stamp, level, text))
        del self.lines[:-500]
        self.line.emit(stamp, level, text)


def worker_name() -> str:
    return f"agent · {socket.gethostname()}"

