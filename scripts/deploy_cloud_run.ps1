# Deploy TerraSentinel to Cloud Run (build in Cloud Build â€” no local Docker required).
#
# Prerequisites:
#   1. gcloud auth login
#   2. An OPEN billing account linked to the project (Cloud Run will not deploy without it)
#   3. backend/.env with TS_ADMIN_PASSWORD and TS_GEMINI_API_KEY set
#
# Usage (AI Builder Cup project â€” billing must be OPEN):
#   .\scripts\deploy_cloud_run.ps1
#   .\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery
#
# Production posture:
#   - max-instances=1 (sessions/rate-limits are file-backed; one process is the supported topology)
#   - min-instances=1 during judging (optional via -KeepWarm)
#   - TS_TRUST_PROXY=true
#   - secrets for admin password and Gemini key
#   - persistent GCS volume for data/state

[CmdletBinding()]
param(
  [string]$ProjectId = "project-3c4cd22c-ff1e-405d-803",
  [string]$Region = "asia-southeast1",
  [string]$Service = "terrasentinel",
  [string]$Repo = "terrasentinel",
  [string]$BillingAccount = "01E250-7520CE-291BFA",
  [switch]$KeepWarm,
  [switch]$SkipBuild,
  [switch]$EnableBigQuery
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# gcloud.ps1 writes progress to the error stream; with Stop that aborts the script. Use cmd shim.
$GcloudCmd = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if (-not (Test-Path $GcloudCmd)) {
  $gc = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($gc) { $GcloudCmd = $gc.Source }
}
if (-not $GcloudCmd -or -not (Test-Path $GcloudCmd)) { throw "gcloud.cmd not found. Install Google Cloud SDK." }

function Invoke-GCloud {
  param(
    [switch]$ShowOutput,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$GcloudArgs
  )
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  # gcloud prints progress on stderr; that must not trip $ErrorActionPreference=Stop.
  if ($ShowOutput) {
    & $GcloudCmd @GcloudArgs
  } else {
    & $GcloudCmd @GcloudArgs 1>$null 2>$null
  }
  $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
  $ErrorActionPreference = $prev
  return $code
}

function Read-DotEnv([string]$path) {
  $map = @{}
  if (-not (Test-Path $path)) { return $map }
  # Use foreach/continue (return inside ForEach-Object can exit the whole function on PS 5.1).
  foreach ($line in Get-Content $path) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $k, $v = $line.Split('=', 2)
    $map[$k.Trim()] = $v
  }
  return $map
}

Write-Host "==> Project $ProjectId Â· region $Region"
Invoke-GCloud config set project $ProjectId | Out-Null

$billing = (& $GcloudCmd billing projects describe $ProjectId --format='value(billingEnabled)' 2>$null)
$acctOpen = (& $GcloudCmd billing accounts describe $BillingAccount --format='value(open)' 2>$null)
if ($billing -ne "True" -or $acctOpen -ne "True") {
  throw @"
Billing is not open on project $ProjectId (billingEnabled=$billing, account $BillingAccount open=$acctOpen).
Cloud Run, Artifact Registry and Cloud Build require an OPEN billing account.

Fix (console only â€” CLI cannot reopen a closed account):
  1. https://console.cloud.google.com/billing/01E250-7520CE-291BFA?project=$ProjectId
  2. Reopen / restore "My Billing Account" (01E250-7520CE-291BFA)
  3. Confirm the project is linked, then re-run:
       .\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery
"@
}

Write-Host "==> Enabling APIs"
$apis = @(
  "run.googleapis.com",
  "artifactregistry.googleapis.com",
  "cloudbuild.googleapis.com",
  "secretmanager.googleapis.com",
  "iam.googleapis.com",
  "aiplatform.googleapis.com",
  "storage.googleapis.com"
)
if ($EnableBigQuery) { $apis += "bigquery.googleapis.com" }
foreach ($api in $apis) {
  Write-Host "    $api"
  $code = Invoke-GCloud services enable $api --project $ProjectId
  if ($code -ne 0) {
    Start-Sleep -Seconds 5
    $code = Invoke-GCloud services enable $api --project $ProjectId
    if ($code -ne 0) { throw "Failed to enable $api" }
  }
}

Write-Host "==> Reading backend/.env"
try {
  $envPath = Join-Path $Root "backend\.env"
  Write-Host "    path=$envPath exists=$([bool](Test-Path $envPath))"
  $envMap = Read-DotEnv $envPath
  Write-Host "    keys=$($envMap.Keys -join ',')"
  $adminUser = if ($envMap["TS_ADMIN_USER"]) { $envMap["TS_ADMIN_USER"] } else { "admin" }
  $adminPass = $envMap["TS_ADMIN_PASSWORD"]
  $geminiKey = $envMap["TS_GEMINI_API_KEY"]
  Write-Host "    adminUser=$adminUser adminPassLen=$($adminPass.Length) geminiKeyLen=$($geminiKey.Length)"
  if (-not $adminPass) { throw "Set TS_ADMIN_PASSWORD in backend/.env before deploying." }
  if (-not $geminiKey) { Write-Warning "TS_GEMINI_API_KEY empty - work orders will use the template fallback." }
} catch {
  Write-Host "FATAL while reading .env: $($_.Exception.Message)"
  Write-Host $_.ScriptStackTrace
  exit 1
}

function Test-GCloudExists {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GcloudArgs)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  # Discard output; existence is decided only by exit code.
  [void](& $GcloudCmd @GcloudArgs 1>$null 2>$null)
  $ok = ($LASTEXITCODE -eq 0)
  $ErrorActionPreference = $prev
  return $ok
}

Write-Host "==> Artifact Registry"
if (-not (Test-GCloudExists artifacts repositories describe $Repo --location=$Region --format='value(name)')) {
  $code = Invoke-GCloud artifacts repositories create $Repo --repository-format=docker --location=$Region --description="TerraSentinel images"
  # 0 = created; non-zero is OK if the repo already exists (race / flaky describe).
  if ($code -ne 0 -and -not (Test-GCloudExists artifacts repositories describe $Repo --location=$Region --format='value(name)')) {
    throw "Failed to create Artifact Registry repo"
  }
}

$Sa = "terrasentinel-run@$ProjectId.iam.gserviceaccount.com"
if (-not (Test-GCloudExists iam service-accounts describe $Sa --format='value(email)')) {
  Write-Host "==> Service account"
  $code = Invoke-GCloud iam service-accounts create terrasentinel-run --display-name="TerraSentinel Cloud Run"
  if ($code -ne 0) { throw "Failed to create service account" }
}
[void](Invoke-GCloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$Sa" --role="roles/logging.logWriter" --condition=None)
[void](Invoke-GCloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$Sa" --role="roles/secretmanager.secretAccessor" --condition=None)
if ($EnableBigQuery) {
  [void](Invoke-GCloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$Sa" --role="roles/bigquery.dataEditor" --condition=None)
  [void](Invoke-GCloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$Sa" --role="roles/bigquery.jobUser" --condition=None)
}

function Upsert-Secret([string]$name, [string]$value) {
  if (-not (Test-GCloudExists secrets describe $name --format='value(name)')) {
    $code = Invoke-GCloud secrets create $name --replication-policy=automatic
    if ($code -ne 0) { throw "Failed to create secret $name" }
  }
  $tmp = New-TemporaryFile
  Set-Content -Path $tmp -Value $value -NoNewline
  $code = Invoke-GCloud secrets versions add $name --data-file="$tmp"
  Remove-Item $tmp -Force
  if ($code -ne 0) { throw "Failed to add secret version $name" }
  [void](Invoke-GCloud secrets add-iam-policy-binding $name --member="serviceAccount:$Sa" --role="roles/secretmanager.secretAccessor" --quiet)
}

Write-Host "==> Secrets"
Upsert-Secret "ts-admin-password" $adminPass
if ($geminiKey) { Upsert-Secret "ts-gemini-api-key" $geminiKey }

$Bucket = "$ProjectId-terrasentinel-state"
if (-not (Test-GCloudExists storage buckets describe "gs://$Bucket" --format='value(name)')) {
  Write-Host "==> State bucket gs://$Bucket"
  $code = Invoke-GCloud storage buckets create "gs://$Bucket" --location=$Region --uniform-bucket-level-access
  if ($code -ne 0) { throw "Failed to create state bucket" }
}
[void](Invoke-GCloud storage buckets add-iam-policy-binding "gs://$Bucket" --member="serviceAccount:$Sa" --role="roles/storage.objectAdmin")

$Image = "$Region-docker.pkg.dev/$ProjectId/$Repo/$Service"
if (-not $SkipBuild) {
  Write-Host "==> Cloud Build (this can take several minutes)"
  $code = Invoke-GCloud builds submit --config cloudbuild.yaml --substitutions="_REGION=$Region,_REPO=$Repo,_IMAGE=$Service" .
  if ($code -ne 0) { throw "Cloud Build failed" }
}

$min = if ($KeepWarm) { 1 } else { 0 }
# Credentials for judges live in the Cup submission deck — never on the public login page.
$envVars = "TS_TRUST_PROXY=true,TS_PROXY_HOPS=1,TS_AUTH_ENABLED=true,TS_SHOW_LOGIN_HINT=false,TS_ADMIN_USER=$adminUser,TS_GCP_PROJECT=$ProjectId,TS_GCP_REGION=$Region"
if ($EnableBigQuery) {
  $envVars += ",TS_DATA_BACKEND=bigquery,TS_BQ_DATASET=terrasentinel,TS_BQ_LOCATION=US"
}

$secrets = "TS_ADMIN_PASSWORD=ts-admin-password:latest"
if ($geminiKey) { $secrets += ",TS_GEMINI_API_KEY=ts-gemini-api-key:latest" }

Write-Host "==> Cloud Run deploy (max-instances=1)"
# Pass args as one array — backtick-splatting into RemainingArguments can drop flags under PS 5.1.
$deployArgs = @(
  "run", "deploy", $Service,
  "--image=${Image}:latest",
  "--region=$Region",
  "--platform=managed",
  "--service-account=$Sa",
  "--allow-unauthenticated",
  "--port=8080",
  "--memory=2Gi",
  "--cpu=2",
  "--concurrency=40",
  "--max-instances=1",
  "--min-instances=$min",
  "--timeout=300",
  "--set-env-vars=$envVars",
  "--set-secrets=$secrets",
  "--add-volume=name=state,type=cloud-storage,bucket=$Bucket",
  "--add-volume-mount=volume=state,mount-path=/srv/terrasentinel/data/state",
  "--execution-environment=gen2"
)
$code = Invoke-GCloud -ShowOutput @deployArgs
if ($code -ne 0) { throw "Cloud Run deploy failed" }

$url = & $GcloudCmd run services describe $Service --region=$Region --format='value(status.url)'
Write-Host ""
Write-Host "Deployed: $url"
Write-Host "Sign in as $adminUser with the password from backend/.env"
Write-Host "Topology: max-instances=1 Â· state on gs://$Bucket Â· TRUST_PROXY on"
if ($EnableBigQuery) {
  Write-Host "BigQuery backend enabled - tables already loaded for this project."
}
