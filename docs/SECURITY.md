# TerraSentinel security notes

Scope: the API (`backend/app`) and the UI it serves. Findings and their status are in `docs/AUDIT_2026-10.md`. This file says what is protected, how, and what you must do when you deploy it.

## 1. Who can do what

Sign-in is on by default. Three roles, each including the one before it:

| Role | Can |
| --- | --- |
| Viewer | Read the map, sites, alerts, outlooks, brief, trends, work orders that exist, data sources and public datasets. |
| Analyst | Everything above, plus act on alerts (acknowledge, assign, escalate, resolve, reopen), draft work orders, export data. |
| Admin | Everything above, plus upload and fetch data, add regions, fetch or delete public datasets, reset to demo data, run BigQuery checks and sync, manage people, read the security log. |

The UI hides what a role cannot use, but the server is the authority: every route checks the role (`require_role`) and returns 403 otherwise. Alert actions record the signed-in person, not a name sent by the browser.

## 2. Accounts and sessions

- Passwords: scrypt with a per-password salt; minimum 10 characters; never logged or returned. Wrong-password and unknown-user answers are identical and take similar time.
- Sessions: a random token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` over https). Only the SHA-256 of the token is stored server-side, so a copy of the state files does not yield usable sessions. Default lifetime 12 hours (`TS_SESSION_TTL_H`).
- Changing or resetting a password, disabling an account or changing its role ends that person's sessions at once.
- Lockout: after 5 wrong passwords (`TS_LOGIN_MAX_FAILURES`) the username from that client address is blocked for 5 minutes (`TS_LOGIN_LOCKOUT_S`). Locks are per username and address so a stranger cannot lock out a real user from elsewhere.
- Audit log: sign-ins, failures, lockouts, sign-outs, account and password changes, as JSON lines in `data/state`. Admins read it under Users & access.
- First run: an administrator is created from `TS_ADMIN_USER` / `TS_ADMIN_PASSWORD`. If no password is set one is generated and written once to `data/state/initial_admin_password.txt`. Change it after first sign-in and delete that file.

## 3. Requests from other websites (CSRF)

Every state-changing request must carry `X-Requested-With: TerraSentinel`, which a browser will not add to a cross-site request without a CORS pre-flight that the API refuses. Requests with a foreign `Origin` are also rejected. Cookies are `SameSite=Lax` as a third layer.

## 4. Fetching links and downloading public data

Link import and public datasets make the server fetch URLs, which is the classic SSRF risk. Defences, all in `app/services/data/connectors.py`:

- https only (plain http only with `TS_ALLOW_HTTP_FETCH=true`).
- The host is resolved once. Every resulting address must be globally routable (`ipaddress.is_global`), which refuses private, loopback, link-local, carrier-grade NAT (100.64/10), documentation, multicast and similar ranges, and also IPv6 forms that embed an IPv4 address (IPv4-mapped, 6to4, Teredo, NAT64).
- The connection then goes to that exact address (with the original `Host` and TLS server name), so DNS cannot answer differently between the check and the fetch.
- Redirects are followed manually, up to a limit, and each hop goes through the same checks.
- Size cap while streaming, timeout, and content-type and format validation before anything is stored.
- Public datasets only come from a fixed catalog of USGS addresses; the region form builds a USGS query from numbers, never from free text.

## 5. Data integrity

- All workspace writes happen under one lock inside a transaction with a backup. A failure rolls back; a crash mid-write is repaired on the next start. Two simultaneous imports cannot lose each other's rows.
- Uploaded text that becomes a name or note is stripped of control characters and bounded. File names are reduced to a safe display name.
- Hostile JSON (deep nesting, huge numbers) returns a clean 400, not a crash.
- Public data never feeds the risk score. It is shown as context and labelled as such.

## 6. Transport and browser hardening

Every response carries a request id and: `Content-Security-Policy` (own origin plus the Esri tile host; no inline scripts), `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors none`, `Referrer-Policy`, a restrictive `Permissions-Policy`, and HSTS over https. Unexpected errors return a generic 500 with the request id; details go to the log only. A coarse per-client rate limit covers the whole API and sensitive routes have tighter ones.

## 7. Secrets

- `backend/.env` holds the Gemini key and admin password and is gitignored (`.env`, `.env.*`, service-account and credentials files). `.env.example` has no real values.
- The Gemini key never goes to the browser; the model only sees tool results.
- A Gemini (AI Studio) key is not a Google Cloud credential. BigQuery needs `gcloud auth application-default login` or a service-account key outside the repository (`TS_GOOGLE_CREDENTIALS_FILE`).

## 8. Before you expose it to a network

1. Serve it over https (a load balancer or Cloud Run gives you this) and set `TS_TRUST_PROXY=true`, `TS_PROXY_HOPS=<number of proxies>` so lockouts and rate limits see real client addresses. Do not set these when clients reach the API directly: the forwarded header can then be forged.
2. Set a strong `TS_ADMIN_PASSWORD` before first start, or read and delete the generated file. Create named accounts; do not share the admin one.
3. Keep `TS_AUTH_ENABLED` at its default (true). Turning it off makes every visitor an administrator.
4. Put `data/state` on a persistent volume if you run in a container, or accounts reset on every restart.
5. Keep keys out of the image and the repository; pass them as environment variables or a secret manager.
6. Restrict the container's outbound network to what you need (Google APIs, USGS, Open-Meteo, Esri tiles) as defence in depth for the fetch features.

## 9. Known limits

- **One process.** Accounts, sessions, lockouts and rate limits are kept in the process and the state files. Run a single instance (or a single worker). A shared store (a database or Redis) is the next step for several instances.
- **No multi-factor sign-in or single sign-on.** For a larger deployment put the app behind an identity-aware proxy (for example Cloud IAP) or add OIDC.
- **`style-src 'unsafe-inline'`.** The UI sets inline styles (React style props, MapLibre). Scripts are not inline.
- **Dependencies.** Versions are pinned in `backend/requirements.lock`. An automated vulnerability scan (`pip-audit`) could not be run on the development machine (blocked by Windows Application Control), so it has not been done. Run it in CI.
- **The container image has not been built or run.** Docker was not available where this was developed.
- **Live Google services are unverified**: BigQuery (no Google Cloud credentials were available) and a full Gemini-written work order (free-tier quota). See `docs/TEST_CHECKLIST.md`.
- This is decision support for qualified engineers, not a certified safety system.
