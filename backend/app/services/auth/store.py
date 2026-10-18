"""Users, sessions and the audit trail, kept as small JSON files under ``settings.state_dir``.

Sessions are server-side: the browser holds a random token, the server keeps only its SHA-256. Signing out
therefore really ends the session, and a leaked state file cannot be replayed as a cookie.

This store assumes ONE API process (the default and what Cloud Run runs with max-instances=1 for the demo).
Scaling out needs a shared store; the interface is small on purpose so Firestore or BigQuery can replace it.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

ROLES = ("viewer", "analyst", "admin")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,39}$")
AUDIT_MAX_BYTES = 5 * 1024 * 1024

_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root() -> Path:
    p = Path(settings.state_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(name: str, default):
    p = _root() / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write(name: str, obj) -> None:
    p = _root() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    tmp.replace(p)


def normalise(username: str) -> str:
    return (username or "").strip().lower()


# ---- users -------------------------------------------------------------------------------------


def list_users() -> list[dict]:
    with _LOCK:
        return list(_read("users.json", []))


def get_user(username: str) -> dict | None:
    key = normalise(username)
    return next((u for u in list_users() if u["username"] == key), None)


def save_user(user: dict) -> None:
    with _LOCK:
        rows = [u for u in _read("users.json", []) if u["username"] != user["username"]]
        rows.append(user)
        _write("users.json", sorted(rows, key=lambda u: u["username"]))


def public(user: dict) -> dict:
    return {k: user.get(k) for k in ("username", "display_name", "role", "disabled", "created_at", "last_login")}


# ---- sessions ----------------------------------------------------------------------------------


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(username: str, ip: str, user_agent: str, ttl_s: float) -> tuple[str, float]:
    token = secrets.token_urlsafe(32)
    exp = time.time() + ttl_s
    with _LOCK:
        sessions = _prune(_read("sessions.json", {}))
        sessions[_digest(token)] = {"username": username, "exp": exp, "created": now_iso(), "ip": ip, "ua": user_agent[:160]}
        _write("sessions.json", sessions)
    return token, exp


def _prune(sessions: dict) -> dict:
    now = time.time()
    return {k: v for k, v in sessions.items() if v["exp"] > now}


def session_user(token: str) -> str | None:
    if not token:
        return None
    s = _read("sessions.json", {}).get(_digest(token))
    if not s or s["exp"] <= time.time():
        return None
    return s["username"]


def end_session(token: str) -> None:
    with _LOCK:
        sessions = _read("sessions.json", {})
        if sessions.pop(_digest(token), None) is not None:
            _write("sessions.json", _prune(sessions))


def end_user_sessions(username: str, except_token: str | None = None) -> int:
    """Sign a user out everywhere (password change, role change, disabling). Returns how many ended."""
    keep = _digest(except_token) if except_token else None
    with _LOCK:
        sessions = _read("sessions.json", {})
        gone = [k for k, v in sessions.items() if v["username"] == username and k != keep]
        for k in gone:
            del sessions[k]
        if gone:
            _write("sessions.json", _prune(sessions))
        return len(gone)


# ---- audit trail -------------------------------------------------------------------------------


def audit(event: str, actor: str, ip: str = "", detail: str = "") -> None:
    """Append one line. Never raises: failing to log must not turn a sign-in into an error."""
    try:
        with _LOCK:
            p = _root() / "audit.jsonl"
            if p.exists() and p.stat().st_size > AUDIT_MAX_BYTES:
                p.replace(p.with_suffix(".jsonl.1"))
            line = json.dumps({"at": now_iso(), "event": event, "actor": actor, "ip": ip, "detail": detail[:300]})
            with p.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError:
        pass


def recent_audit(limit: int = 100) -> list[dict]:
    p = _root() / "audit.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out[::-1]
