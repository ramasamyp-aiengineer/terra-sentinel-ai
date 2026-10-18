# Cloud Run deploy · TerraSentinel AI

## Target

| | |
| --- | --- |
| Account | `ramasamy.p2105@gmail.com` |
| Project | My First Project · `project-3c4cd22c-ff1e-405d-803` |
| Billing | My Billing Account · `01E250-7520CE-291BFA` |
| Region | `asia-southeast1` (Singapore Demo Day) |

## Live (18 Oct 2026)

| | |
| --- | --- |
| Billing | **Open** (`01E250-7520CE-291BFA`) |
| URL | https://terrasentinel-598899050820.asia-southeast1.run.app |
| Region | `asia-southeast1` |
| Backend | BigQuery (`terrasentinel` dataset) |
| Topology | `max-instances=1`, GCS state volume, `TS_TRUST_PROXY=true` |

Sign in as `admin` with the password in `backend/.env` (Secret Manager: `ts-admin-password`).

## Redeploy

```powershell
.\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery
```

## Honest limits after go-live

- One process only (sessions / lockouts / rate limits are file-backed).
- Analyst cannot upload (admin only) - by design.
- Demo data is synthetic; label that for judges.
