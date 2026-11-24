"""What the whole app shares while signed in: the session, the Profiles and the one picked."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from . import tasks
from .api import Api, ApiError, Session, TokenProfile
from .config import config

ALL = ""  # the "All Profiles" choice


class AppState(QObject):
    profiles_changed = Signal()
    profile_changed = Signal(str)  # profile id ("" = All Profiles)
    data_changed = Signal()  # an application changed here (status, Apply): pages reload
    signed_out = Signal(str)  # reason
    online_changed = Signal(bool)

    def __init__(self, api: Api):
        super().__init__()
        self.api = api
        self.session: Session = api.session
        self.profiles: list[dict] = []
        self.profile_id: str = ALL
        self.online = True
        api.on_signed_out = lambda reason: self._signed_out_from_thread(reason)
        self._renew = QTimer(self)
        self._renew.setInterval(4 * 60_000)
        self._renew.timeout.connect(self._renew_now)
        if self.session.mode == "account":
            self._renew.start()

    # Thread-safe: the API calls this from a worker thread.
    def _signed_out_from_thread(self, reason: str) -> None:
        QTimer.singleShot(0, lambda: self.signed_out.emit(reason))

    def _renew_now(self) -> None:
        tasks.run(self.api.renew_now, lambda _r: self._set_online(True), self._renew_failed, owner=self)

    def _renew_failed(self, error: Exception) -> None:
        if isinstance(error, ApiError) and error.is_offline:
            self._set_online(False)

    def _set_online(self, online: bool) -> None:
        if online != self.online:
            self.online = online
            self.online_changed.emit(online)

    def mark_online(self) -> None:
        self._set_online(True)

    def report_error(self, error: Exception) -> None:
        self._set_online(not (isinstance(error, ApiError) and error.is_offline))

    # ------------------------------------------------------------------ Profiles
    @property
    def can_pick_all(self) -> bool:
        return self.session.mode == "account"

    def load_profiles(self) -> None:
        def done(rows):
            self._set_online(True)
            self.profiles = [self._normalise(p) for p in (rows or [])]
            ids = {p["id"] for p in self.profiles if not p.get("revoked")}
            wanted = config.last_profile
            if self.session.mode == "token":
                if wanted not in ids:
                    wanted = next(iter(ids), ALL)
            elif wanted not in ids:
                wanted = ALL
            self.profiles_changed.emit()
            self.set_profile(wanted, force=True)

        tasks.run(self.api.profiles, done, self.report_error, owner=self)

    @staticmethod
    def _normalise(p: dict) -> dict:
        name = p.get("displayName") or " ".join(x for x in (p.get("firstName"), p.get("lastName")) if x) or "Profile"
        return {"id": p.get("id"), "name": name, "revoked": bool(p.get("revoked")), "note": p.get("note") or p.get("headline") or ""}

    def set_profile(self, profile_id: str, force: bool = False) -> None:
        if profile_id == self.profile_id and not force:
            return
        self.profile_id = profile_id
        config.last_profile = profile_id
        self.profile_changed.emit(profile_id)

    @property
    def profile_name(self) -> str:
        if not self.profile_id:
            return "All Profiles"
        return next((p["name"] for p in self.profiles if p["id"] == self.profile_id), "Profile")

    @property
    def request_profile(self) -> str | None:
        """The Profile to scope a call to: None means every Profile in reach (account mode only)."""
        if self.profile_id:
            return self.profile_id
        if self.session.mode == "token":
            return next((p["id"] for p in self.profiles if not p.get("revoked")), None)
        return None

    # ------------------------------------------------------------------ tokens
    def add_token(self, info: dict, token: str) -> TokenProfile:
        """Keep a checked token (Settings / sign-in) and its Profile."""
        from . import vault
        from .api import mask_token

        profile = info.get("profile") or {}
        tp = TokenProfile(
            profile_id=str(profile.get("id")),
            profile_name=str(profile.get("name") or "Profile"),
            mask=mask_token(token),
            label=str(info.get("label") or ""),
            expires_at=info.get("expiresAt"),
        )
        self.session.tokens[tp.profile_id] = token
        self.session.token_profiles[tp.profile_id] = tp
        vault.save_profile_token(self.session.server, tp.profile_id, token)
        self._save_entries()
        return tp

    def remove_token(self, profile_id: str) -> None:
        from . import vault

        self.session.tokens.pop(profile_id, None)
        self.session.token_profiles.pop(profile_id, None)
        vault.forget_profile_token(self.session.server, profile_id)
        self._save_entries()
        if self.profile_id == profile_id:
            self.profile_id = ALL

    def _save_entries(self) -> None:
        config.set_token_entries(self.session.server, [p.to_entry() for p in self.session.token_profiles.values()])
