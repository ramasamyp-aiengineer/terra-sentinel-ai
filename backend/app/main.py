from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.auth_routes import router as auth_router
from app.api.data_routes import router as data_router
from app.api.deps import require_user
from app.api.intel_routes import router as intel_router
from app.api.routes import router
from app.core.config import REPO_ROOT, settings
from app.core.middleware import hardening

VERSION = "0.3.0"
log = logging.getLogger("terrasentinel")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # 0. Refuse a half-configured BigQuery mode: empty project means every data call fails later.
    if settings.data_backend.lower() == "bigquery" and not (settings.gcp_project or "").strip():
        log.error(
            "Misconfigured: TS_DATA_BACKEND=bigquery but TS_GCP_PROJECT is empty. "
            "Set TS_GCP_PROJECT=your-project-id or set TS_DATA_BACKEND=local. "
            "Diagnose with: python -m app.services.bq.doctor"
        )
    # 1. A crash in the middle of an import leaves a backup of the last good workspace: put it back.
    try:
        from app.services.data.repo import recover_workspace

        if recover_workspace():
            from app.services import runtime

            runtime.refresh_all()
            log.warning("Restored the data workspace from the backup left by an interrupted import.")
    except Exception:  # noqa: BLE001
        log.exception("workspace recovery failed")
    # 2. Make sure someone can sign in.
    try:
        from app.services.auth.service import bootstrap_admin

        bootstrap_admin()
    except Exception:  # noqa: BLE001
        log.exception("could not create the first administrator")
    # 3. Prefetch live BigQuery/local frames + current rankings first, then warm history.
    #    (Warming 16 historical passes immediately after deploy starved Command Center for ~1–2 min.)
    try:
        from app.services import runtime

        runtime.prefetch_in_background()
    except Exception:  # noqa: BLE001 - never block startup on a warm-up
        log.exception("could not start hot-path prefetch")
    yield


app = FastAPI(
    title="TerraSentinel API",
    version=VERSION,
    description="Early-warning and inspection triage for ground motion under critical infrastructure.",
    lifespan=lifespan,
)

app.add_middleware(BaseHTTPMiddleware, dispatch=hardening)
app.add_middleware(  # outermost, so CORS headers also appear on errors produced inside
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Requested-With", "X-Request-ID"],
)

# Sign-in endpoints are public; everything else needs a signed-in user (finer role checks sit on the routes).
guard = [Depends(require_user)]
app.include_router(auth_router)
app.include_router(router, dependencies=guard)
app.include_router(intel_router, dependencies=guard)
app.include_router(data_router, dependencies=guard)


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness: the process is up. Used by the platform to decide whether to restart it."""
    return {"status": "ok", "version": VERSION}


@app.get("/readyz", include_in_schema=False)
def readyz():
    """Readiness: data loads and the engine runs. Used by the platform to decide whether to send traffic."""
    if settings.data_backend.lower() == "bigquery" and not (settings.gcp_project or "").strip():
        return JSONResponse(
            {
                "status": "not-ready",
                "reason": "TS_DATA_BACKEND=bigquery requires TS_GCP_PROJECT",
            },
            status_code=503,
        )
    try:
        from app.services.data.repo import get_repo
        from app.services.detection.pipeline import run_pipeline

        repo = get_repo()
        # Prefer a cheap probe: regions must load. Full pipeline may still be prefetching.
        n_regions = len(repo.regions())
        try:
            n_sites = len(run_pipeline())
        except Exception:  # noqa: BLE001
            n_sites = -1
        return {
            "status": "ready",
            "backend": repo.backend,
            "regions": n_regions,
            "sites": n_sites,
            "auth": settings.auth_enabled,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("readiness check failed")
        return JSONResponse({"status": "not-ready", "reason": exc.__class__.__name__}, status_code=503)


# ---- optional: serve the built UI from the same origin (single-container deployment) --------------


def _static_dir() -> Path | None:
    for cand in ([Path(settings.static_dir)] if settings.static_dir else []) + [REPO_ROOT / "frontend" / "dist"]:
        if (cand / "index.html").exists():
            return cand
    return None


class SPAFiles(StaticFiles):
    """Static files with client-side-routing fallback; never answers /api/* with HTML."""

    async def get_response(self, path, scope):
        if path.startswith("api/") or path in ("api", "healthz", "readyz"):
            raise HTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # content-hashed file names
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


_dist = _static_dir()
if _dist is not None:
    app.mount("/", SPAFiles(directory=str(_dist), html=True), name="ui")
