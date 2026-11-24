"""The connection to the romva server: sign-in, renewing it, and every API call.

Two ways to connect (Settings → Connection):

* **Account** — email and password (and the authenticator code for the Super
  Admin). The server answers with a 15-minute access token and a renew
  (refresh) token. The access token is renewed in the background before it
  runs out; each renewal swaps the refresh token for a new one, which is kept
  in Windows Credential Manager when "Keep me signed in" is on.
* **Tokens** — one Profile token (``rmv_…``) per Profile, added by the bidder.
  Every call for a Profile carries that Profile's token. A token deleted by the
  admin answers 401, and that Profile shows as "Revoked by admin".

All calls are blocking (httpx) and are made off the UI thread (tasks.py).
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import APP_NAME, APP_VERSION, vault
from .config import config

REFRESH_COOKIE = "ge_refresh"
_log = logging.getLogger("romvahub.api")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message

    @property
    def is_auth(self) -> bool:
        return self.status == 401

    @property
    def is_offline(self) -> bool:
        return self.status == 0


class MfaRequired(Exception):
    def __init__(self, challenge: dict):
        super().__init__("Enter the code from your authenticator app.")
        self.challenge = challenge


def _jwt_exp(token: str) -> float:
    """When an access token runs out (its `exp`), or 0 if it can't be read."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except (IndexError, ValueError, TypeError):
        return 0.0


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if data.get("message"):
            return str(data["message"])
    vercel = response.headers.get("x-vercel-error")
    if vercel:
        return f"The server is switched off on Vercel ({response.status_code} {vercel})."
    return f"{response.status_code} {response.reason_phrase}"


@dataclass
class TokenProfile:
    profile_id: str
    profile_name: str
    mask: str
    label: str = ""
    expires_at: str | None = None
    revoked: bool = False

    def to_entry(self) -> dict:
        return {
            "profileId": self.profile_id,
            "profileName": self.profile_name,
            "mask": self.mask,
            "label": self.label,
            "expiresAt": self.expires_at,
            "revoked": self.revoked,
        }

    @staticmethod
    def from_entry(entry: dict) -> "TokenProfile":
        return TokenProfile(
            profile_id=str(entry.get("profileId")),
            profile_name=str(entry.get("profileName") or "Profile"),
            mask=str(entry.get("mask") or "rmv_…"),
            label=str(entry.get("label") or ""),
            expires_at=entry.get("expiresAt"),
            revoked=bool(entry.get("revoked")),
        )


def mask_token(token: str) -> str:
    return f"{token[:6]}…{token[-2:]}" if len(token) > 10 else "rmv_…"


@dataclass
class Session:
    """Who this app is connected as, and the keys to prove it."""

    server: str
    mode: str = "account"  # "account" | "token"
    user: dict | None = None
    keep_signed_in: bool = True
    _access: str | None = None
    _access_exp: float = 0.0
    _refresh: str | None = None
    tokens: dict[str, str] = field(default_factory=dict)  # profileId -> rmv_ token
    token_profiles: dict[str, TokenProfile] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def is_admin(self) -> bool:
        return self.mode == "account" and bool(self.user) and self.user.get("role") == "admin"

    @property
    def display_name(self) -> str:
        if self.mode == "token":
            return "Token mode"
        if not self.user:
            return ""
        email = str(self.user.get("email", ""))
        return email.split("@")[0] if email else "Signed in"

    @property
    def role_label(self) -> str:
        return "Admin" if self.is_admin else "Bidder"


class Api:
    """Every call the app makes. Thread-safe."""

    def __init__(self, session: Session):
        self.session = session
        self._http = httpx.Client(
            base_url=session.server,
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json"},
        )
        # Called (from any thread) when the sign-in can no longer be renewed.
        self.on_signed_out = None

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ low level
    def _send(self, method: str, path: str, *, bearer: str | None = None, params=None, json_body=None,
              cookies: dict | None = None, timeout: float | None = None) -> httpx.Response:
        headers = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        started = time.monotonic()
        try:
            response = self._http.request(
                method, path, params=params, json=json_body, headers=headers,
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as error:
            _log.warning("%s %s -> no answer (%s)", method, path, error)
            raise ApiError(0, f"Could not reach {self.session.server}: {error}") from error
        finally:
            # The server also sets cookies for the website; this app uses headers only.
            self._http.cookies.clear()
        # Debug log: method, path, query, status and time. Never the tokens or bodies.
        ms = int((time.monotonic() - started) * 1000)
        level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
        if _log.isEnabledFor(level):
            query = f"?{httpx.QueryParams(params)}" if params else ""
            detail = f"  {_error_message(response)}" if response.status_code >= 400 else ""
            _log.log(level, "%s %s%s -> %s (%d ms)%s", method, path, query, response.status_code, ms, detail)
        return response

    def _bearer(self, profile_id: str | None) -> str:
        s = self.session
        if s.mode == "token":
            pid = profile_id or next(iter(s.tokens), None)
            token = s.tokens.get(pid or "")
            if not token:
                raise ApiError(401, "No token for this Profile. Add one in Settings → Connection.")
            return token
        with s._lock:
            if not s._access or s._access_exp - time.time() < 60:
                self._refresh_locked()
            return s._access or ""

    def _refresh_locked(self) -> None:
        """Swap the refresh token for a new pair. Caller holds the session lock."""
        s = self.session
        if not s._refresh:
            raise ApiError(401, "Please sign in again.")
        response = self._send("POST", "/api/auth/refresh", json_body={"refreshToken": s._refresh})
        if response.status_code != 200:
            message = _error_message(response)
            if response.status_code in (401, 403):
                s._refresh = None
                s._access = None
                vault.forget_refresh_token(s.server)
                if self.on_signed_out:
                    self.on_signed_out(message)
            raise ApiError(response.status_code, message)
        data = response.json()
        self._take_tokens(data)

    def _take_tokens(self, data: dict) -> None:
        s = self.session
        s._access = data.get("accessToken")
        s._access_exp = _jwt_exp(s._access or "")
        s._refresh = data.get("refreshToken") or s._refresh
        if data.get("user"):
            s.user = data["user"]
        if s._refresh and s.keep_signed_in:
            vault.save_refresh_token(s.server, s._refresh)

    def renew_now(self) -> None:
        """Renew the access token if it runs out soon (the background timer calls this)."""
        if self.session.mode != "account":
            return
        with self.session._lock:
            if not self.session._access or self.session._access_exp - time.time() < 180:
                self._refresh_locked()

    def request(self, method: str, path: str, *, params=None, json_body=None, profile_id: str | None = None,
                raw: bool = False, timeout: float | None = None) -> Any:
        for attempt in (1, 2):
            bearer = self._bearer(profile_id)
            response = self._send(method, path, bearer=bearer, params=params, json_body=json_body, timeout=timeout)
            if response.status_code == 401 and self.session.mode == "account" and attempt == 1:
                with self.session._lock:
                    self.session._access = None
                continue
            if response.status_code == 401 and self.session.mode == "token" and profile_id:
                self._mark_revoked(profile_id)
            if response.status_code >= 400:
                raise ApiError(response.status_code, _error_message(response))
            if raw:
                return response
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return response.text
        raise ApiError(401, "Please sign in again.")

    def _mark_revoked(self, profile_id: str) -> None:
        tp = self.session.token_profiles.get(profile_id)
        if tp and not tp.revoked:
            tp.revoked = True
            config.set_token_entries(self.session.server, [p.to_entry() for p in self.session.token_profiles.values()])

    # ------------------------------------------------------------------ sign-in
    def login(self, email: str, password: str) -> dict:
        response = self._send("POST", "/api/auth/login", json_body={"email": email, "password": password})
        if response.status_code >= 400:
            raise ApiError(response.status_code, _error_message(response))
        data = response.json()
        if "mfa" in data:
            raise MfaRequired(data["mfa"])
        with self.session._lock:
            self._take_tokens(data)
        return data["user"]

    def verify_mfa(self, challenge_id: str, code: str) -> dict:
        response = self._send("POST", "/api/auth/login/verify", json_body={"challengeId": challenge_id, "code": code})
        if response.status_code >= 400:
            raise ApiError(response.status_code, _error_message(response))
        data = response.json()
        with self.session._lock:
            self._take_tokens(data)
        return data["user"]

    def resume_saved_sign_in(self) -> dict | None:
        """Sign in again with the renew token saved in Credential Manager, if any."""
        saved = vault.refresh_token(self.session.server)
        if not saved:
            return None
        self.session._refresh = saved
        with self.session._lock:
            self._refresh_locked()
        return self.session.user

    def logout(self) -> None:
        s = self.session
        if s.mode == "account" and s._refresh:
            try:
                self._send("POST", "/api/auth/logout", cookies={REFRESH_COOKIE: s._refresh}, timeout=10)
            except ApiError:
                pass
        s._refresh = None
        s._access = None
        s.user = None
        vault.forget_refresh_token(s.server)

    def access_token(self) -> str:
        """A current access token (account mode), for the Resume Maker."""
        return self._bearer(None)

    def check_token(self, token: str) -> dict:
        """What a Profile token opens: { token: { id, label, expiresAt, profile: { id, name } } }."""
        response = self._send("GET", "/api/auth/me", bearer=token)
        if response.status_code >= 400:
            raise ApiError(response.status_code, _error_message(response))
        data = response.json()
        if not isinstance(data, dict) or "token" not in data:
            raise ApiError(400, "This is not a Romva Profile token.")
        return data["token"]

    def ping(self) -> bool:
        try:
            response = self._send("GET", "/health", timeout=10)
            return response.status_code < 500
        except ApiError:
            return False

    # ------------------------------------------------------------------ data
    def profiles(self) -> list[dict]:
        s = self.session
        if s.mode == "token":
            return [
                {"id": p.profile_id, "displayName": p.profile_name, "revoked": p.revoked, "note": f"Token {p.mask}"}
                for p in s.token_profiles.values()
            ]
        if s.is_admin:
            return self.request("GET", "/api/admin/profiles")
        return self.request("GET", "/api/profiles")

    def bids_page(self, *, profile_id: str | None, page: int, page_size: int, statuses: list[str] | None = None,
                  search: str = "") -> dict:
        params: dict[str, Any] = {"page": page, "pageSize": page_size, "sort": "bidDate"}
        if statuses:
            params["statuses"] = ",".join(statuses)
        if search:
            params["search"] = search
        if profile_id and self.session.mode == "account":
            params["profileId"] = profile_id
        return self.request("GET", "/api/bids", params=params, profile_id=profile_id)

    def bids_count(self, *, profile_id: str | None, statuses: list[str] | None) -> int:
        data = self.bids_page(profile_id=profile_id, page=1, page_size=1, statuses=statuses)
        return int(data.get("total", 0)) if isinstance(data, dict) else 0

    def bids_version(self, profile_id: str | None) -> str:
        params = {"profileId": profile_id} if profile_id and self.session.mode == "account" else None
        data = self.request("GET", "/api/bids/version", params=params, profile_id=profile_id)
        return str((data or {}).get("version", ""))

    def set_status(self, bid_ids: list[str], status: str, profile_id: str | None) -> int:
        data = self.request("POST", "/api/bids/bulk/status", json_body={"ids": bid_ids, "status": status},
                            profile_id=profile_id)
        return int((data or {}).get("updated", 0))

    def document(self, bid_id: str, kind: str, fmt: str, profile_id: str | None) -> tuple[bytes, str]:
        """The Resume ("resume") or cover letter ("cover-letter") as PDF or Word: (bytes, file name)."""
        response = self.request("GET", f"/api/bids/{bid_id}/{kind}", params={"format": fmt}, profile_id=profile_id,
                                raw=True, timeout=120)
        name = _filename(response.headers.get("content-disposition", "")) or f"{kind}.{fmt}"
        return response.content, name

    def profile_detail(self, profile_id: str) -> dict:
        return self.request("GET", f"/api/profiles/{profile_id}", profile_id=profile_id)

    def save_profile(self, profile_id: str, body: dict) -> dict:
        return self.request("PUT", f"/api/profiles/{profile_id}", json_body=body, profile_id=profile_id)

    def prompts(self, profile_id: str) -> dict:
        return self.request("GET", f"/api/profiles/{profile_id}/prompts", profile_id=profile_id)

    def save_prompts(self, profile_id: str, body: dict) -> dict:
        return self.request("PUT", f"/api/profiles/{profile_id}/prompts", json_body=body, profile_id=profile_id)

    def avoid(self, profile_id: str) -> dict:
        return self.request("GET", f"/api/profiles/{profile_id}/avoid", profile_id=profile_id)

    def save_avoid(self, profile_id: str, body: dict) -> dict:
        return self.request("PUT", f"/api/profiles/{profile_id}/avoid", json_body=body, profile_id=profile_id)


def _filename(disposition: str) -> str | None:
    """The file name in a Content-Disposition header (RFC 5987 `filename*` first)."""
    from urllib.parse import unquote

    for part in disposition.split(";"):
        part = part.strip()
        if part.lower().startswith("filename*="):
            value = part.split("=", 1)[1]
            if "''" in value:
                value = value.split("''", 1)[1]
            return unquote(value.strip('"'))
    for part in disposition.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            return part.split("=", 1)[1].strip('"')
    return None
