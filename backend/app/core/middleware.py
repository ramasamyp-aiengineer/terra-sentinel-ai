"""Cross-cutting HTTP behaviour: request ids, access log, security headers, CSRF defence, global rate brake,
and a last-resort error handler that never leaks internals."""
from __future__ import annotations

import logging
import re
import time
import uuid
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.net import client_ip
from app.core.ratelimit import allow

log = logging.getLogger("terrasentinel.http")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "TerraSentinel"
_RID_OK = re.compile(r"^[A-Za-z0-9._-]{6,64}$")

# Served only with the built UI. The map needs Esri tiles (img/connect) and blob workers.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://server.arcgisonline.com; connect-src 'self' https://server.arcgisonline.com; "
    "font-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:  # same-site navigations and non-browser clients send none
        return True
    host = urlparse(origin).netloc
    allowed = {o.strip() for o in settings.cors_origins.split(",") if o.strip()}
    return host == request.headers.get("host", "") or origin in allowed


def _error(status: int, detail: str, rid: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail, "request_id": rid}, status_code=status, headers=headers)


async def hardening(request: Request, call_next):
    rid = request.headers.get("x-request-id", "")
    rid = rid if _RID_OK.match(rid) else uuid.uuid4().hex[:12]
    request.state.request_id = rid
    started = time.perf_counter()
    path = request.url.path
    is_api = path.startswith("/api/")

    response = None
    if is_api and request.method not in SAFE_METHODS:
        # A cross-site form or script cannot add this header without a CORS preflight, which we do not grant.
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE or not _origin_allowed(request):
            response = _error(403, "This request was blocked as a possible cross-site request.", rid)
    if response is None and is_api and not allow(f"api:{client_ip(request)}", settings.api_rate_per_min, 60):
        response = _error(429, "Too many requests - please wait a moment.", rid, {"Retry-After": "30"})

    if response is None:
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - the boundary: log with context, answer with a safe message
            log.exception("unhandled error rid=%s %s %s", rid, request.method, path)
            response = _error(500, "Something went wrong on our side. Quote this reference if you report it.", rid)

    ms = (time.perf_counter() - started) * 1000
    h = response.headers
    h["X-Request-ID"] = rid
    h["Server-Timing"] = f"app;dur={ms:.0f}"
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "same-origin"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
    if is_api:
        h["Cache-Control"] = "no-store"  # responses are per-user and may be sensitive
    else:
        h.setdefault("Content-Security-Policy", CSP)
    if request.url.scheme == "https" or (settings.trust_proxy and request.headers.get("x-forwarded-proto") == "https"):
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path != "/healthz":
        user = getattr(request.state, "principal", None)
        who = getattr(user, "username", "-") if user not in (None, "unset") else "-"
        log.info("%s %s %s %.0fms rid=%s user=%s ip=%s", request.method, path, response.status_code, ms, rid, who, client_ip(request))
    return response
