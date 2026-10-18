"""Request dependencies: who is calling, and are they allowed to."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response

from app.core.config import settings
from app.core.net import client_ip
from app.services.auth import service as auth

COOKIE = "ts_session"


def session_token(request: Request) -> str:
    return request.cookies.get(COOKIE, "")


def current_principal(request: Request) -> auth.Principal | None:
    if not settings.auth_enabled:
        return auth.LOCAL
    cached = getattr(request.state, "principal", "unset")
    if cached != "unset":
        return cached
    p = auth.principal_for(session_token(request))
    request.state.principal = p
    return p


def require_user(request: Request) -> auth.Principal:
    p = current_principal(request)
    if p is None:
        raise HTTPException(401, "Sign in to continue.")
    return p


def require_role(role: str):
    """Dependency factory: the caller must hold at least ``role`` (viewer < analyst < admin)."""

    def dep(p: auth.Principal = Depends(require_user)) -> auth.Principal:
        if not p.can(role):
            raise HTTPException(403, f"Your role ({p.role}) cannot do this. It needs {role} access.")
        return p

    return dep


def _secure(request: Request) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    if settings.trust_proxy and request.headers.get("x-forwarded-proto", "").lower() == "https":
        return True
    return request.url.scheme == "https"


def set_session_cookie(request: Request, response: Response, token: str, max_age: int) -> None:
    response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, samesite="lax", secure=_secure(request), path="/")


def clear_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=_secure(request))


__all__ = ["COOKIE", "client_ip", "current_principal", "require_user", "require_role", "session_token", "set_session_cookie", "clear_session_cookie"]
