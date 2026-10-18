"""Password hashing (scrypt, standard library) and the password policy."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1  # ~16 MB and ~50 ms per hash: slow enough to hurt guessing, fast enough for sign-in
MIN_LENGTH = 10
_COMMON = {
    "password", "password1", "password123", "passw0rd", "qwerty123", "letmein123", "welcome123", "admin12345",
    "administrator", "terrasentinel", "1234567890", "iloveyou123", "changeme123",
}


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P, dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, want = stored.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
            dklen=32, maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(got, base64.b64decode(want))
    except (ValueError, TypeError):
        return False


_dummy: str | None = None


def burn_time(password: str) -> None:
    """Spend the same time as a real check, so an unknown username cannot be told apart by response time."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password(secrets.token_urlsafe(8))
    verify_password(password, _dummy)


def policy_errors(password: str, username: str = "") -> list[str]:
    """Plain-language reasons a password is not acceptable (empty list = fine)."""
    errs: list[str] = []
    if len(password) < MIN_LENGTH:
        errs.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > 128:
        errs.append("Use at most 128 characters.")
    low = password.lower()
    if low in _COMMON or (username and low == username.lower()):
        errs.append("That password is too easy to guess.")
    if len(set(password)) < 5:
        errs.append("Use a greater variety of characters.")
    return errs


def generate_password() -> str:
    return secrets.token_urlsafe(15)
