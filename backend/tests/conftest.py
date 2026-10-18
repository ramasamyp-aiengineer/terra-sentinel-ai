"""Test isolation: never touch the developer's real workspace / state, never start background warm-ups."""
from __future__ import annotations

import pytest
from fastapi import testclient

from app.core.config import settings

# Existing API tests are about data and maths, not identity: they run with sign-in off. The auth tests switch it
# on (see the `auth_on` fixture). Every test client sends the anti-CSRF header the API requires on writes.
settings.auth_enabled = False
_orig_init = testclient.TestClient.__init__


def _init(self, *args, headers=None, **kwargs):
    _orig_init(self, *args, headers={"X-Requested-With": "TerraSentinel", **(headers or {})}, **kwargs)


testclient.TestClient.__init__ = _init


@pytest.fixture(scope="session", autouse=True)
def _isolated_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("ts")
    old = (settings.workspace_dir, settings.state_dir, settings.warm_on_change, settings.cache_dir, settings.public_dir)
    # Tests must be deterministic and free: never call Gemini / live BigQuery even if .env is production-shaped.
    old_ai = (settings.gemini_api_key, settings.gcp_project, settings.data_backend)
    settings.gemini_api_key = ""
    settings.gcp_project = ""
    settings.data_backend = "local"
    settings.workspace_dir = root / "workspace"
    settings.state_dir = root / "state"
    settings.cache_dir = root / "cache"
    settings.public_dir = root / "public"
    settings.warm_on_change = False
    from app.services.data.repo import get_repo

    get_repo.cache_clear()
    yield
    settings.workspace_dir, settings.state_dir, settings.warm_on_change, settings.cache_dir, settings.public_dir = old
    settings.gemini_api_key, settings.gcp_project, settings.data_backend = old_ai
    get_repo.cache_clear()


def _reset_everything():
    from app.services import runtime
    from app.services.data import state

    state.clear_state_cache()
    runtime.refresh_all()


@pytest.fixture()
def workspace(tmp_path):
    """A fresh, empty writable workspace + state store on top of the demo data."""
    old = (settings.workspace_dir, settings.state_dir)
    settings.workspace_dir = tmp_path / "workspace"
    settings.state_dir = tmp_path / "state"
    _reset_everything()
    yield tmp_path
    settings.workspace_dir, settings.state_dir = old
    _reset_everything()


@pytest.fixture()
def auth_on(tmp_path):
    """Sign-in switched on with an empty, isolated user store and clean throttles."""
    from app.core import ratelimit
    from app.services.auth import service as auth

    old = (settings.auth_enabled, settings.state_dir, settings.admin_password, settings.login_max_failures)
    settings.auth_enabled = True
    settings.state_dir = tmp_path / "authstate"
    settings.admin_password = "Correct-Horse-Battery-9"
    settings.login_max_failures = 5
    auth.reset_throttle()
    ratelimit.reset()
    auth.bootstrap_admin()
    yield
    settings.auth_enabled, settings.state_dir, settings.admin_password, settings.login_max_failures = old
    auth.reset_throttle()
    ratelimit.reset()
