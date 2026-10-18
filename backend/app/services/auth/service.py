"""Sign-in, sessions, roles and user administration."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.core.config import settings
from app.services.auth import passwords, store

log = logging.getLogger("terrasentinel.auth")

ROLES = store.ROLES
RANK = {r: i for i, r in enumerate(ROLES)}


class AuthError(Exception):
    """A sign-in or user-management problem that is safe to show to the person who caused it."""

    def __init__(self, message: str, status: int = 400, retry_after: int | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class Principal:
    username: str
    display_name: str
    role: str

    def can(self, role: str) -> bool:
        return RANK[self.role] >= RANK[role]


# What the app uses when sign-in is switched off (local development only).
LOCAL = Principal("local", "Local developer", "admin")


# ---- brute-force protection ----------------------------------------------------------------------

_fail_lock = threading.Lock()
_failures: dict[str, list[float]] = {}  # "user|ip" -> timestamps of recent failures


def _key(username: str, ip: str) -> str:
    return f"{store.normalise(username)}|{ip}"


def _locked_for(key: str) -> int:
    """Seconds left on a lockout, 0 if the caller may try."""
    now = time.monotonic()
    with _fail_lock:
        recent = [t for t in _failures.get(key, []) if now - t < settings.login_lockout_s]
        _failures[key] = recent
        if len(recent) >= settings.login_max_failures:
            return max(1, int(settings.login_lockout_s - (now - recent[0])))
        return 0


def _fail(key: str) -> None:
    with _fail_lock:
        _failures.setdefault(key, []).append(time.monotonic())
        if len(_failures) > 5000:  # bound memory under a spray of random usernames
            for k in [k for k, v in _failures.items() if not v or time.monotonic() - v[-1] > settings.login_lockout_s]:
                _failures.pop(k, None)


def reset_throttle() -> None:
    with _fail_lock:
        _failures.clear()


# ---- sign in / out ---------------------------------------------------------------------------------


def login(username: str, password: str, ip: str, user_agent: str = "") -> tuple[dict, str, float]:
    """Returns (public user, session token, expiry epoch). Raises AuthError with a deliberately vague message."""
    key = _key(username, ip)
    wait = _locked_for(key)
    if wait:
        store.audit("login_locked", store.normalise(username), ip)
        raise AuthError(f"Too many attempts. Try again in {max(1, wait // 60)} minute(s).", 429, retry_after=wait)

    user = store.get_user(username)
    ok = False
    if user and not user.get("disabled"):
        ok = passwords.verify_password(password, user["pw_hash"])
    else:
        passwords.burn_time(password)  # unknown or disabled: take as long as a real check
    if not ok:
        _fail(key)
        store.audit("login_failed", store.normalise(username), ip)
        raise AuthError("Incorrect username or password.", 401)

    with _fail_lock:
        _failures.pop(key, None)
    user["last_login"] = store.now_iso()
    store.save_user(user)
    token, exp = store.create_session(user["username"], ip, user_agent, settings.session_ttl_h * 3600)
    store.audit("login", user["username"], ip)
    return store.public(user), token, exp


def logout(token: str, principal: Principal | None, ip: str = "") -> None:
    if token:
        store.end_session(token)
    if principal:
        store.audit("logout", principal.username, ip)


def principal_for(token: str | None) -> Principal | None:
    username = store.session_user(token or "")
    if not username:
        return None
    user = store.get_user(username)
    if not user or user.get("disabled"):
        return None
    return Principal(user["username"], user.get("display_name") or user["username"], user["role"])


# ---- user administration -------------------------------------------------------------------------------


def _validate_username(username: str) -> str:
    u = store.normalise(username)
    if not store.USERNAME_RE.match(u):
        raise AuthError("Username must be 3-40 characters: letters, numbers, dot, dash, underscore or @.")
    return u


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise AuthError(f"Role must be one of: {', '.join(ROLES)}.")
    return role


def _admins(exclude: str | None = None) -> int:
    return sum(1 for u in store.list_users() if u["role"] == "admin" and not u.get("disabled") and u["username"] != exclude)


def create_user(actor: Principal, username: str, display_name: str, role: str, password: str, ip: str = "") -> dict:
    u = _validate_username(username)
    _validate_role(role)
    if store.get_user(u):
        raise AuthError("That username is already taken.", 409)
    errs = passwords.policy_errors(password, u)
    if errs:
        raise AuthError(" ".join(errs), 422)
    user = {
        "username": u,
        "display_name": (display_name or u).strip()[:60],
        "role": role,
        "pw_hash": passwords.hash_password(password),
        "disabled": False,
        "created_at": store.now_iso(),
        "last_login": None,
    }
    store.save_user(user)
    store.audit("user_created", actor.username, ip, f"{u} as {role}")
    return store.public(user)


def update_user(
    actor: Principal, username: str, *, role: str | None = None, disabled: bool | None = None,
    password: str | None = None, display_name: str | None = None, ip: str = "",
) -> dict:
    user = store.get_user(username)
    if not user:
        raise AuthError("No such user.", 404)
    changes = []
    if role is not None and role != user["role"]:
        _validate_role(role)
        if user["role"] == "admin" and _admins(exclude=user["username"]) == 0:
            raise AuthError("There must always be at least one active administrator.", 409)
        user["role"] = role
        changes.append(f"role={role}")
    if disabled is not None and disabled != bool(user.get("disabled")):
        if disabled and user["username"] == actor.username:
            raise AuthError("You cannot disable your own account.", 409)
        if disabled and user["role"] == "admin" and _admins(exclude=user["username"]) == 0:
            raise AuthError("There must always be at least one active administrator.", 409)
        user["disabled"] = disabled
        changes.append("disabled" if disabled else "enabled")
    if display_name is not None:
        user["display_name"] = display_name.strip()[:60] or user["username"]
    if password is not None:
        errs = passwords.policy_errors(password, user["username"])
        if errs:
            raise AuthError(" ".join(errs), 422)
        user["pw_hash"] = passwords.hash_password(password)
        changes.append("password reset")
    store.save_user(user)
    if changes and any(c != "enabled" for c in changes):
        store.end_user_sessions(user["username"])  # a changed role or password must not ride on old sessions
    store.audit("user_updated", actor.username, ip, f"{user['username']}: {', '.join(changes) or 'name'}")
    return store.public(user)


def change_own_password(principal: Principal, current: str, new: str, keep_token: str | None, ip: str = "") -> None:
    user = store.get_user(principal.username)
    if not user or not passwords.verify_password(current, user["pw_hash"]):
        store.audit("password_change_failed", principal.username, ip)
        raise AuthError("Your current password is not right.", 403)
    errs = passwords.policy_errors(new, user["username"])
    if errs:
        raise AuthError(" ".join(errs), 422)
    if passwords.verify_password(new, user["pw_hash"]):
        raise AuthError("Choose a password you have not used here before.", 422)
    user["pw_hash"] = passwords.hash_password(new)
    store.save_user(user)
    ended = store.end_user_sessions(user["username"], except_token=keep_token)
    store.audit("password_changed", user["username"], ip, f"{ended} other session(s) ended")


# ---- first run ----------------------------------------------------------------------------------------------


def bootstrap_admin() -> str | None:
    """Create the first administrator if there are no users. Returns a generated password (never stored in plain text
    anywhere except a one-time file for the operator), or None."""
    if not settings.auth_enabled or store.list_users():
        return None
    username = store.normalise(settings.admin_user) or "admin"
    generated = not settings.admin_password
    password = settings.admin_password or passwords.generate_password()
    user = {
        "username": username,
        "display_name": "Administrator",
        "role": "admin",
        "pw_hash": passwords.hash_password(password),
        "disabled": False,
        "created_at": store.now_iso(),
        "last_login": None,
    }
    store.save_user(user)
    store.audit("bootstrap_admin", "system", "", username)
    if not generated:
        log.warning("Created administrator %r from TS_ADMIN_PASSWORD. Change it after first sign-in.", username)
        return None
    note = settings.state_dir / "initial_admin_password.txt"
    note.write_text(
        f"TerraSentinel first-run administrator\nusername: {username}\npassword: {password}\n"
        "Sign in, change the password, then delete this file.\n",
        encoding="utf-8",
    )
    log.warning("Created administrator %r with a generated password, saved to %s (delete it after first sign-in).", username, note)
    return password
