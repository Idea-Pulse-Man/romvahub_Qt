"""Opening jobs in the bidder's own Chrome, where the Alt+V extension fills the forms."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from .config import config

CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str:
    saved = config.chrome_path
    if saved and Path(saved).exists():
        return saved
    for candidate in CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def open_url(url: str) -> None:
    # The app's own Chrome (browser.py) once Romva Apply is in it: that is where the bidder bids.
    from . import browser

    try:
        if browser.extension_installed() and browser.open_urls(url):
            return
    except OSError:
        pass
    chrome = find_chrome()
    if chrome:
        try:
            subprocess.Popen([chrome, url], close_fds=True)
            return
        except OSError:
            pass
    webbrowser.open(url)


def apply_url(bid_ids: list[str]) -> str:
    """The page the Alt+V extension listens on: it opens each job in its own tab and fills it."""
    return f"{config.server_url}/applications#romva-apply={','.join(bid_ids)}"


def apply(bid_ids: list[str]) -> None:
    if bid_ids:
        open_url(apply_url(bid_ids))
