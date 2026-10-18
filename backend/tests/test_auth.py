"""Sign-in, sessions, roles, lockout, CSRF defence and the audit trail."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.auth import passwords, store

PW = "Correct-Horse-Battery-9"
pytestmark = pytest.mark.usefixtures("auth_on")


def new_client(**kw) -> TestClient:
    return TestClient(app, **kw)


def signed_in(username="admin", password=PW) -> TestClient:
    c = new_client()
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def make_user(admin: TestClient, username: str, role: str, password: str = "Sturdy-Passphrase-77"):
    r = admin.post("/api/auth/users", json={"username": username, "display_name": username.title(), "role": role, "password": password})
    assert r.status_code == 200, r.text
    return password


# ---- passwords -------------------------------------------------------------------------------------------


def test_password_hash_is_salted_and_verifies():
    a, b = passwords.hash_password("hunter2-hunter2"), passwords.hash_password("hunter2-hunter2")
    assert a != b and a.startswith("scrypt$")
    assert passwords.verify_password("hunter2-hunter2", a) and not passwords.verify_password("nope", a)
    assert not passwords.verify_password("x", "garbage") and not passwords.verify_password("x", "scrypt$1$2")


@pytest.mark.parametrize("pw", ["short", "password123", "aaaaaaaaaaaa", "x" * 200])
def test_weak_passwords_are_rejected(pw):
    assert passwords.policy_errors(pw, "admin")


def test_a_reasonable_passphrase_is_accepted():
    assert passwords.policy_errors("Sturdy-Passphrase-77", "admin") == []


# ---- gate ------------------------------------------------------------------------------------------------------


def test_api_requires_sign_in_but_health_and_me_do_not():
    c = new_client()
    assert c.get("/healthz").status_code == 200
    me = c.get("/api/auth/me").json()
    assert me["auth_enabled"] is True and me["user"] is None
    for path in ("/api/meta", "/api/sites", "/api/alerts", "/api/data/status", "/api/regions"):
        assert c.get(path).status_code == 401, path


def test_login_sets_httponly_cookie_and_unlocks_the_api():
    c = new_client()
    r = c.post("/api/auth/login", json={"username": "Admin", "password": PW})  # username is case-insensitive
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "ts_session=" in cookie
    assert c.get("/api/meta").status_code == 200
    assert c.get("/api/auth/me").json()["user"]["username"] == "admin"
    assert "pw_hash" not in r.text


def test_wrong_password_and_unknown_user_give_the_same_vague_answer():
    c = new_client()
    a = c.post("/api/auth/login", json={"username": "admin", "password": "wrong-password-1"})
    b = c.post("/api/auth/login", json={"username": "nobody", "password": "wrong-password-1"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_logout_really_ends_the_session():
    c = signed_in()
    token = c.cookies.get("ts_session")
    assert c.post("/api/auth/logout").status_code == 200
    stale = new_client(cookies={"ts_session": token})  # replay the old cookie
    assert stale.get("/api/meta").status_code == 401


def test_session_secret_is_stored_only_as_a_hash():
    c = signed_in()
    token = c.cookies.get("ts_session")
    raw = (settings.state_dir / "sessions.json").read_text(encoding="utf-8")
    assert token not in raw


def test_forged_and_garbage_cookies_are_rejected():
    for cookie in ("", "abc", "A" * 200, "../../etc/passwd"):
        assert new_client(cookies={"ts_session": cookie}).get("/api/meta").status_code == 401


def test_expired_session_is_rejected(monkeypatch):
    c = signed_in()
    import time

    real = time.time
    monkeypatch.setattr(store.time, "time", lambda: real() + settings.session_ttl_h * 3600 + 5)
    assert c.get("/api/meta").status_code == 401


# ---- brute force ---------------------------------------------------------------------------------------------------


def test_repeated_failures_lock_the_account_for_that_client():
    c = new_client()
    for _ in range(settings.login_max_failures):
        assert c.post("/api/auth/login", json={"username": "admin", "password": "bad-password-x1"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "admin", "password": PW})  # even the right one is refused now
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_lockout_is_per_username_so_others_are_unaffected():
    c = new_client()
    for _ in range(settings.login_max_failures):
        c.post("/api/auth/login", json={"username": "ghost", "password": "bad-password-x1"})
    assert c.post("/api/auth/login", json={"username": "admin", "password": PW}).status_code == 200


# ---- roles ---------------------------------------------------------------------------------------------------------


def test_viewer_can_read_but_not_act_or_manage():
    admin = signed_in()
    pw = make_user(admin, "vera", "viewer")
    v = signed_in("vera", pw)
    assert v.get("/api/sites").status_code == 200
    assert v.post("/api/alerts/action", json={"alert_id": "x", "action": "acknowledge"}).status_code == 403
    assert v.post("/api/sites/anything/workorder?mode=template").status_code == 403
    assert v.post("/api/data/reset-demo").status_code == 403
    assert v.post("/api/data/fetch-rain", json={"region_id": "IN"}).status_code == 403
    assert v.get("/api/data/export/points").status_code == 403
    assert v.get("/api/auth/users").status_code == 403
    assert v.get("/api/auth/audit").status_code == 403


def test_analyst_can_act_on_alerts_but_not_change_data():
    admin = signed_in()
    pw = make_user(admin, "andy", "analyst")
    a = signed_in("andy", pw)
    assert a.post("/api/alerts/action", json={"alert_id": "nope", "action": "acknowledge"}).status_code == 404  # allowed, alert unknown
    assert a.get("/api/data/export/points").status_code == 200
    assert a.post("/api/data/reset-demo").status_code == 403
    assert a.get("/api/auth/users").status_code == 403


def test_alert_actor_cannot_be_forged_by_the_client():
    admin = signed_in()
    pw = make_user(admin, "andy", "analyst")
    a = signed_in("andy", pw)
    alerts = a.get("/api/alerts").json()["alerts"]
    if not alerts:
        pytest.skip("demo data produced no alerts")
    r = a.post("/api/alerts/action", json={"alert_id": alerts[0]["alert_id"], "action": "acknowledge", "actor": "the-ceo"})
    assert r.status_code == 200
    assert r.json()["history"][0]["actor"] == "andy"


# ---- CSRF ------------------------------------------------------------------------------------------------------------


def test_writes_without_the_anti_csrf_header_are_blocked():
    c = signed_in()
    bare = TestClient(app, cookies=dict(c.cookies), headers={"X-Requested-With": ""})
    assert bare.post("/api/data/reset-demo").status_code == 403
    assert bare.post("/api/auth/logout").status_code == 403


def test_writes_from_a_foreign_origin_are_blocked():
    c = signed_in()
    r = c.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert c.get("/api/meta").status_code == 200  # still signed in: the blocked request did nothing


def test_same_origin_and_configured_origin_are_allowed():
    c = signed_in()
    r = c.post("/api/auth/password", json={"current_password": "x", "new_password": "y"}, headers={"Origin": "http://localhost:5173"})
    assert "cross-site" not in r.json()["detail"]  # got past the CSRF gate (and then failed on the wrong password)


# ---- user administration -------------------------------------------------------------------------------------------------


def test_admin_creates_lists_and_disables_users():
    admin = signed_in()
    pw = make_user(admin, "dana", "analyst")
    listed = admin.get("/api/auth/users").json()["users"]
    assert {u["username"] for u in listed} == {"admin", "dana"}
    assert all("pw_hash" not in u for u in listed)
    d = signed_in("dana", pw)
    assert admin.patch("/api/auth/users/dana", json={"disabled": True}).status_code == 200
    assert d.get("/api/meta").status_code == 401  # disabling signs them out immediately
    assert new_client().post("/api/auth/login", json={"username": "dana", "password": pw}).status_code == 401


def test_duplicate_and_invalid_users_are_refused():
    admin = signed_in()
    make_user(admin, "dana", "viewer")
    assert admin.post("/api/auth/users", json={"username": "DANA", "role": "viewer", "password": "Sturdy-Passphrase-77"}).status_code == 409
    assert admin.post("/api/auth/users", json={"username": "bad name!", "role": "viewer", "password": "Sturdy-Passphrase-77"}).status_code == 400
    assert admin.post("/api/auth/users", json={"username": "okname", "role": "emperor", "password": "Sturdy-Passphrase-77"}).status_code == 400
    assert admin.post("/api/auth/users", json={"username": "okname", "role": "viewer", "password": "short"}).status_code == 422


def test_the_last_administrator_cannot_be_removed_or_disabled():
    admin = signed_in()
    assert admin.patch("/api/auth/users/admin", json={"role": "viewer"}).status_code == 409
    assert admin.patch("/api/auth/users/admin", json={"disabled": True}).status_code == 409


def test_role_change_takes_effect_and_ends_old_sessions():
    admin = signed_in()
    pw = make_user(admin, "dana", "analyst")
    d = signed_in("dana", pw)
    admin.patch("/api/auth/users/dana", json={"role": "viewer"})
    assert d.get("/api/meta").status_code == 401  # must sign in again to get the new role
    d2 = signed_in("dana", pw)
    assert d2.post("/api/alerts/action", json={"alert_id": "x", "action": "acknowledge"}).status_code == 403


def test_change_own_password_keeps_this_session_and_ends_others():
    admin = signed_in()
    other = signed_in()  # a second browser
    r = admin.post("/api/auth/password", json={"current_password": PW, "new_password": "A-Brand-New-Passphrase-1"})
    assert r.status_code == 200
    assert admin.get("/api/meta").status_code == 200
    assert other.get("/api/meta").status_code == 401
    assert new_client().post("/api/auth/login", json={"username": "admin", "password": PW}).status_code == 401
    assert new_client().post("/api/auth/login", json={"username": "admin", "password": "A-Brand-New-Passphrase-1"}).status_code == 200


def test_change_password_needs_the_current_password_and_a_strong_new_one():
    c = signed_in()
    assert c.post("/api/auth/password", json={"current_password": "wrong", "new_password": "A-Brand-New-Passphrase-1"}).status_code == 403
    assert c.post("/api/auth/password", json={"current_password": PW, "new_password": "short"}).status_code == 422
    assert c.post("/api/auth/password", json={"current_password": PW, "new_password": PW}).status_code == 422


def test_audit_trail_records_security_events_without_secrets():
    admin = signed_in()
    new_client().post("/api/auth/login", json={"username": "admin", "password": "bad-password-x1"})
    make_user(admin, "dana", "viewer")
    events = admin.get("/api/auth/audit").json()["events"]
    kinds = {e["event"] for e in events}
    assert {"login", "login_failed", "user_created"} <= kinds
    blob = str(events)
    assert PW not in blob and "bad-password-x1" not in blob and "scrypt$" not in blob


# ---- first run / switch ---------------------------------------------------------------------------------------------------


def test_generated_first_run_password_is_saved_for_the_operator_not_logged_in_state():
    settings.state_dir = settings.state_dir / "fresh"
    settings.admin_password = ""
    pw = __import__("app.services.auth.service", fromlist=["x"]).bootstrap_admin()
    assert pw and len(pw) >= 16
    note = settings.state_dir / "initial_admin_password.txt"
    assert pw in note.read_text(encoding="utf-8")
    assert pw not in (settings.state_dir / "users.json").read_text(encoding="utf-8")
    assert new_client().post("/api/auth/login", json={"username": "admin", "password": pw}).status_code == 200


def test_bootstrap_does_nothing_when_users_exist():
    from app.services.auth import service as auth

    assert auth.bootstrap_admin() is None
    assert len(store.list_users()) == 1


def test_readiness_and_health_stay_public_and_carry_security_headers():
    c = new_client()
    r = c.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]
    assert c.get("/api/meta").headers["cache-control"] == "no-store"


def test_error_responses_never_leak_internals(monkeypatch):
    c = signed_in()
    from app.api import routes

    def boom():
        raise RuntimeError("secret internal path C:\\Users\\x\\.env")

    monkeypatch.setattr(routes, "get_repo", boom)
    r = TestClient(app, cookies=dict(c.cookies), raise_server_exceptions=False).get("/api/meta")
    assert r.status_code == 500
    assert "secret" not in r.text and r.json()["request_id"]
