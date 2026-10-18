"""Client address helper shared by rate limiting, login lockout and the audit log."""
from __future__ import annotations

from fastapi import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    """The caller's address.

    Behind a reverse proxy every request appears to come from the proxy, so rate limits and lockouts would
    apply to everyone at once. With ``TS_TRUST_PROXY`` the entry ``TS_PROXY_HOPS`` from the right of
    ``X-Forwarded-For`` is used: everything left of it is client-supplied and can be forged, so it is ignored.
    """
    if settings.trust_proxy:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        hops = max(1, settings.proxy_hops)
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"
