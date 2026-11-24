"""Secrets in Windows Credential Manager (keyring): the sign-in's renew token and the Profile tokens.

Each secret is its own credential ("romvahub" service), so no single entry
grows past Credential Manager's size limit. Windows encrypts them for the
signed-in Windows user; copying the app folder to another PC copies none.
If Credential Manager can't be reached, secrets are kept in memory only for
this run (the user signs in again next time).
"""

from __future__ import annotations

import logging

SERVICE = "romvahub"
_memory: dict[str, str] = {}
log = logging.getLogger(__name__)

try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
except Exception:  # pragma: no cover - keyring missing
    keyring = None  # type: ignore[assignment]
    KeyringError = PasswordDeleteError = Exception  # type: ignore[misc,assignment]


def _name(kind: str, server: str, extra: str = "") -> str:
    return f"{kind}|{server.lower()}|{extra}"


def get(kind: str, server: str, extra: str = "") -> str | None:
    name = _name(kind, server, extra)
    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE, name)
            if value:
                return value
        except KeyringError as error:  # pragma: no cover
            log.warning("Credential Manager read failed: %s", error)
    return _memory.get(name)


def put(kind: str, server: str, value: str, extra: str = "") -> None:
    name = _name(kind, server, extra)
    if keyring is not None:
        try:
            keyring.set_password(SERVICE, name, value)
            _memory.pop(name, None)
            return
        except KeyringError as error:  # pragma: no cover
            log.warning("Credential Manager write failed, keeping it in memory: %s", error)
    _memory[name] = value


def delete(kind: str, server: str, extra: str = "") -> None:
    name = _name(kind, server, extra)
    _memory.pop(name, None)
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE, name)
        except (KeyringError, PasswordDeleteError):
            pass


# The two kinds of secret.
def refresh_token(server: str) -> str | None:
    return get("refresh", server)


def save_refresh_token(server: str, token: str) -> None:
    put("refresh", server, token)


def forget_refresh_token(server: str) -> None:
    delete("refresh", server)


def profile_token(server: str, profile_id: str) -> str | None:
    return get("token", server, profile_id)


def save_profile_token(server: str, profile_id: str, token: str) -> None:
    put("token", server, token, profile_id)


def forget_profile_token(server: str, profile_id: str) -> None:
    delete("token", server, profile_id)
