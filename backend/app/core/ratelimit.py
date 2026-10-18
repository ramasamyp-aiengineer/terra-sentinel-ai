"""In-memory sliding-window rate limiter (per client address) to protect sign-in, the LLM endpoint and the
cloud bill on a public demo. Swap for Cloud Armor / API Gateway at scale.

``limit(n, s)`` is a per-route dependency; ``allow(key, n, s)`` is the primitive the global middleware uses.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.net import client_ip

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
_MAX_KEYS = 20_000


def allow(key: str, max_calls: int, per_seconds: float) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > per_seconds:
            q.popleft()
        if len(q) >= max_calls:
            return False
        q.append(now)
        if len(_hits) > _MAX_KEYS:
            _shrink(now, per_seconds)
        return True


def _shrink(now: float, per_seconds: float) -> None:
    """Bound memory when a spray of addresses fills the table: drop idle keys, then the least recently seen ones."""
    for k in [k for k, v in _hits.items() if not v or now - v[-1] > per_seconds]:
        _hits.pop(k, None)
    if len(_hits) > _MAX_KEYS:
        keep = int(_MAX_KEYS * 0.9)
        for k, _ in sorted(_hits.items(), key=lambda kv: kv[1][-1])[: len(_hits) - keep]:
            _hits.pop(k, None)


def reset() -> None:
    with _lock:
        _hits.clear()


def limit(max_calls: int, per_seconds: int):
    def dep(request: Request):
        if not allow(f"{request.url.path}:{client_ip(request)}", max_calls, per_seconds):
            raise HTTPException(429, "Too many requests - please wait a moment.", headers={"Retry-After": str(per_seconds)})

    return dep
