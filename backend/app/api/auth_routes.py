"""Sign-in, sign-out, the current user, password change and (admin) user management."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.api import deps
from app.core.config import settings
from app.core.net import client_ip
from app.core.ratelimit import limit
from app.services.auth import passwords, store
from app.services.auth import service as auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _fail(exc: auth.AuthError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return HTTPException(exc.status, str(exc), headers=headers)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", dependencies=[Depends(limit(30, 60))])
def login(body: LoginBody, request: Request, response: Response):
    if not settings.auth_enabled:
        return {"auth_enabled": False, "user": _view(auth.LOCAL)}
    try:
        user, token, exp = auth.login(body.username, body.password, client_ip(request), request.headers.get("user-agent", ""))
    except auth.AuthError as exc:
        raise _fail(exc)
    deps.set_session_cookie(request, response, token, int(exp - time.time()))
    return {"auth_enabled": True, "user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    auth.logout(deps.session_token(request), deps.current_principal(request), client_ip(request))
    deps.clear_session_cookie(request, response)
    return {"ok": True}


def _view(p: auth.Principal) -> dict:
    return {"username": p.username, "display_name": p.display_name, "role": p.role}


@router.get("/me")
def me(request: Request):
    """Never 401: the app calls this on load to decide between the sign-in page and the workspace."""
    p = deps.current_principal(request)
    return {
        "auth_enabled": settings.auth_enabled,
        "user": _view(p) if p else None,
        "roles": list(auth.ROLES),
        "password_min_length": passwords.MIN_LENGTH,
    }


@router.get("/login-hint")
def login_hint():
    """Optional judge/demo credentials for the sign-in page. Off unless TS_SHOW_LOGIN_HINT=true."""
    if not settings.show_login_hint or not settings.auth_enabled:
        return {"enabled": False}
    password = (settings.admin_password or "").strip()
    if not password:
        note = settings.state_dir / "initial_admin_password.txt"
        if note.is_file():
            password = next((ln.strip() for ln in note.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
    if not password:
        return {
            "enabled": True,
            "username": settings.admin_user,
            "password": None,
            "note": "Demo hint is on, but no password is configured. Set TS_ADMIN_PASSWORD.",
        }
    return {
        "enabled": True,
        "username": settings.admin_user,
        "password": password,
        "role": "admin",
        "note": "Local demo hint only. Prefer putting credentials in the submission deck for judges.",
    }


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


@router.post("/password", dependencies=[Depends(limit(10, 60))])
def change_password(body: PasswordBody, request: Request, p: auth.Principal = Depends(deps.require_user)):
    if not settings.auth_enabled:
        raise HTTPException(400, "Sign-in is switched off, so there are no passwords to change.")
    try:
        auth.change_own_password(p, body.current_password, body.new_password, deps.session_token(request), client_ip(request))
    except auth.AuthError as exc:
        raise _fail(exc)
    return {"ok": True}


# ---- administration -----------------------------------------------------------------------------


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    display_name: str = Field("", max_length=60)
    role: str
    password: str = Field(max_length=256)


class UserPatch(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    password: str | None = Field(None, max_length=256)
    display_name: str | None = Field(None, max_length=60)


admin = Depends(deps.require_role("admin"))


@router.get("/users")
def users(_: auth.Principal = admin):
    return {"users": [store.public(u) for u in store.list_users()], "roles": list(auth.ROLES)}


@router.post("/users", dependencies=[Depends(limit(20, 60))])
def create_user(body: NewUser, request: Request, p: auth.Principal = admin):
    try:
        return auth.create_user(p, body.username, body.display_name, body.role, body.password, client_ip(request))
    except auth.AuthError as exc:
        raise _fail(exc)


@router.patch("/users/{username}", dependencies=[Depends(limit(30, 60))])
def update_user(username: str, body: UserPatch, request: Request, p: auth.Principal = admin):
    try:
        return auth.update_user(
            p, username, role=body.role, disabled=body.disabled, password=body.password,
            display_name=body.display_name, ip=client_ip(request),
        )
    except auth.AuthError as exc:
        raise _fail(exc)


@router.get("/audit")
def audit_log(n: int = Query(100, ge=1, le=500, alias="limit"), _: auth.Principal = admin):
    return {"events": store.recent_audit(n)}
