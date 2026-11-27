"""The app's own Chrome: where the bidder bids, and where Resumes are made.

One Chrome profile of the app's own (its sign-ins to ChatGPT, DeepSeek and the job sites stay
there), with the Romva Apply extension (../altv) in it and, if set, a proxy:

* The extension is a copy the app keeps up to date in its data folder: a newer one built into
  the app (or next to it, in the repo) is copied over it, and Chrome is restarted to load it.
  Chrome (137 and later) no longer takes an extension from the command line, so it is added
  once by hand: Developer mode -> Load unpacked -> that folder (the app shows how).
* romva-config.json in that folder tells the extension this computer's name and the server;
  proxy-config.json the proxy's sign-in (the extension answers the proxy's password prompt).
* The proxy: Chrome starts with --proxy-server, and --proxy-bypass-list for the sites the
  bidder lists (none unless the bidder adds them).
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path

from .chrome import find_chrome
from .config import app_dir, config, data_dir

EXTENSION_NAME = "Romva Apply"


def worker_name() -> str:
    """This computer's name on romva.space for the Resume maker in Chrome (the Start window, the queue)."""
    return f"chrome · {socket.gethostname()}"


def profile_dir() -> Path:
    path = data_dir() / "chrome-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extension_dir() -> Path:
    return data_dir() / "romva-apply"


def _version(folder: Path) -> tuple[int, ...]:
    try:
        text = json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig")).get("version", "0")
        return tuple(int(part) for part in str(text).split(".") if part.isdigit())
    except (OSError, ValueError):
        return ()


def version_text(folder: Path | None = None) -> str:
    return ".".join(str(n) for n in _version(folder or extension_dir())) or "—"


def bundled_extension() -> Path | None:
    """The newest Romva Apply the app has: built in (<app>\\altv, build.ps1), else next to it in the repo."""
    for candidate in (app_dir() / "altv", app_dir().parent / "altv"):
        if (candidate / "manifest.json").exists():
            return candidate
    return None


def sync_extension() -> bool:
    """Copies a newer Romva Apply over the app's copy. True when it changed (Chrome must restart to load it)."""
    source = bundled_extension()
    target = extension_dir()
    if not source or (target.exists() and _version(target) >= _version(source)):
        return False
    keep = {name: (target / name).read_bytes() for name in ("romva-config.json", "proxy-config.json") if (target / name).exists()}
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "*.md", "__pycache__"))
    for name, data in keep.items():
        (target / name).write_bytes(data)
    return True


def write_configs() -> None:
    """What the extension reads from its own folder: this computer's name and the server; the proxy's sign-in."""
    folder = extension_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "romva-config.json").write_text(
        json.dumps({"worker": worker_name(), "apiUrl": config.server_url}, indent=2), encoding="utf-8")
    proxy = {"username": config.proxy_user, "password": config.proxy_password} if config.proxy_user else {}
    (folder / "proxy-config.json").write_text(json.dumps(proxy, indent=2), encoding="utf-8")


def extension_installed() -> bool:
    """Whether the app's Chrome profile has the extension loaded (Developer mode -> Load unpacked), from its preferences."""
    wanted = str(extension_dir()).lower().replace("\\", "/")
    for name in ("Secure Preferences", "Preferences"):
        try:
            text = (profile_dir() / "Default" / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if wanted in text.lower().replace("\\\\", "/").replace("\\", "/"):
            return True
    return False


def _arguments(urls: list[str]) -> list[str]:
    args = [f"--user-data-dir={profile_dir()}", "--no-first-run", "--no-default-browser-check"]
    if config.proxy_host and config.proxy_port:
        args.append(f"--proxy-server=http://{config.proxy_host}:{config.proxy_port}")
        bypass = [part.strip() for part in config.proxy_bypass.replace(",", ";").split(";") if part.strip()]
        if bypass:
            args.append(f"--proxy-bypass-list={';'.join(bypass)}")
    return args + urls


def open_urls(*urls: str) -> bool:
    """Opens the app's Chrome (or new tabs in it, when it is open). False when no Chrome was found."""
    chrome = find_chrome()
    if not chrome:
        return False
    sync_extension()
    write_configs()
    subprocess.Popen([chrome, *_arguments(list(urls))], close_fds=True)
    return True


def _profile_processes() -> list[int]:
    """The Chrome processes running with the app's profile."""
    marker = str(profile_dir()).replace("'", "''")
    script = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | "
              f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | ForEach-Object {{ $_.ProcessId }}")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                             timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(line) for line in out.split() if line.strip().isdigit()]


def is_running() -> bool:
    return bool(_profile_processes())


def restart(*urls: str) -> bool:
    """Closes the app's Chrome (only that one) and opens it again: a new Romva Apply or proxy takes effect."""
    for pid in _profile_processes():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return open_urls(*(urls or (f"{config.server_url}/applications",)))


def install_steps() -> str:
    return (f"Add {EXTENSION_NAME} to the app's Chrome once:\n\n"
            "1. In that Chrome window, the page chrome://extensions is open.\n"
            "2. Turn on Developer mode (top right).\n"
            "3. Click Load unpacked and choose this folder:\n"
            f"   {extension_dir()}\n\n"
            "After that the app keeps it up to date by itself.")
