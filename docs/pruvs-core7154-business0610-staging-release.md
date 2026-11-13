# Pruvs staging release: Core v7.1.54 + Business v0.6.10

**STAGING CANDIDATE — not deployed.** No production branch, deployment, customer data, database schema, or environment variable was changed to prepare this release.

- Combined repository: `MelinteB/Pruvio`
- Combined branch: `release/pruvs-platform-v7154-b0610-combined-stage-20261113`
- Standalone Business repository: `MelinteB/Pruvs-Business`
- Standalone Business branch: `release/pruvs-business-v0.6.10-stage-20261113`
- Core rollback branch: `release/pruvs-platform-v7153-b069-combined-stage-20261113`
- Business rollback branch: `release/pruvs-business-v0.6.9-stage-20261113`

## Why this version

Previously, merchant claim listings rendered a **Review receipt** button for customer-code claims that were still locked. Entering a code and reissuing it also required tighter authorization: an old receipt-image view must never authorize a decision after code rotation. The customer side could suppress a failed receipt-status request into an empty list, making claims appear absent.

## Changes

### Core v7.1.54

- Customer receipt claims have distinct **loading / ready / unavailable / disabled** states. If Business cannot confirm claims, saved receipts stay visible, but duplicate submissions are paused.
- In the customer-code pilot, pending claims display **Awaiting merchant verification**; accepted claims display success; rejected claims display the returned reason.
- Pending claims may request a fresh 20-minute code. UI explains that the previous code and merchant review authorization become invalid. The modal keeps the code visible until the customer closes it; it does not refresh mid-display.
- Customer code feature status now also requires `PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED`, to match actual backend acceptance.
- Release metadata, frontend manifest, update banner, service-worker registration query and cache key set to **7.1.54**.
- Added Vitest regression tests for pending claims and failed claim-status retrieval. Retains Core v7.1.53 currency normalization.

### Business v0.6.10

- `GET /v1/merchant/claims` returns per-staff flags `requires_customer_code` and `review_unlocked`. Locked claims are explicitly labelled in the merchant inbox; only unlocked claims display Review.
- A successful claim-code lookup permits that **merchant staff member** to review for 15 minutes. The lookup code expires after 20 minutes; reissuing invalidates the previous code and any previous unlock.
- Approval and rejection require current code unlock **even if that staff member viewed the receipt before the code was reissued**. Legacy claims without a customer code retain their historical flow, but missing consented evidence for a customer-code claim cannot be treated as a legacy exemption.
- Reissue is rejected (409) if claim amount, merchant, consented preview hash, merchant label or receipt date differs from the already pending claim. Neither image nor amount is silently replaced.
- The authenticated, read-only v0.6.9 readiness endpoint remains available.
- No new migrations; b08/b09/b10 remain prerequisites for the complete reward/promotion pilot. No POS/payment integration.

## Windows PowerShell — isolated predeployment verification

Requires Git, Python 3.12, Node.js 22, npm, PostgreSQL client tools only for the later staging-DB step. **Do not execute against production.** The commands below do not touch the existing working directories beyond fetching Git metadata. They add detached, isolated verification worktrees.

```powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $HOME 'Personal\Project'
$coreBranch = 'release/pruvs-platform-v7154-b0610-combined-stage-20261113'
$businessBranch = 'release/pruvs-business-v0.6.10-stage-20261113'
$coreVerify = Join-Path $root 'Pruvs-Core-v7154-Verify'
$businessVerify = Join-Path $root 'Pruvs-Business-v0610-Verify'

$coreCandidates = @(
    (Join-Path $root 'Pruvs-Stage-UX-20261110'),
    (Join-Path $root 'Pruvs')
)
$coreSource = $coreCandidates | Where-Object {
    (Test-Path (Join-Path $_ '.git')) -and
    ((git -C $_ remote get-url origin) -match 'MelinteB/Pruvio(\.git)?$')
} | Select-Object -First 1
if (-not $coreSource) { throw 'Cannot find the MelinteB/Pruvio Core repository. Set $coreSource to its correct path.' }

$businessSource = Join-Path $root 'Pruvs-Business'
if (-not (Test-Path (Join-Path $businessSource '.git'))) {
    git clone 'https://github.com/MelinteB/Pruvs-Business.git' $businessSource
    if ($LASTEXITCODE -ne 0) { throw 'Cloning the Business repository failed.' }
}
if ((git -C $businessSource remote get-url origin) -notmatch 'MelinteB/Pruvs-Business(\.git)?$') {
    throw 'Business remote does not match the intended repository.'
}
foreach ($path in @($coreVerify, $businessVerify)) {
    if (Test-Path $path) { throw "Verification directory already exists: $path" }
}
git -C $coreSource fetch origin $coreBranch
if ($LASTEXITCODE -ne 0) { throw 'Core fetch failed' }
git -C $businessSource fetch origin $businessBranch
if ($LASTEXITCODE -ne 0) { throw 'Business fetch failed' }

$coreSha = (git -C $coreSource rev-parse "origin/$coreBranch").Trim()
$businessSha = (git -C $businessSource rev-parse "origin/$businessBranch").Trim()
git -C $coreSource worktree add --detach $coreVerify $coreSha
if ($LASTEXITCODE -ne 0) { throw 'Core worktree creation failed' }
git -C $businessSource worktree add --detach $businessVerify $businessSha
if ($LASTEXITCODE -ne 0) { throw 'Business worktree creation failed' }
Write-Host "Core staging SHA: $coreSha" -ForegroundColor Cyan
Write-Host "Business staging SHA: $businessSha" -ForegroundColor Cyan

Push-Location (Join-Path $coreVerify 'backend')
try {
    py -3.12 -m venv .stagevenv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is needed' }
    $python = Join-Path (Get-Location) '.stagevenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt -r business-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Core Python dependency install failed' }
    & $python -m pytest -q tests/test_receipt_currency_v7153.py tests/test_pilot_readiness_v069.py tests/test_receipt_code_access_v0610.py tests/test_wallet_legacy_v068.py tests/test_combined_platform_routes.py tests/test_stage_v067.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py
    if ($LASTEXITCODE -ne 0) { throw 'Combined backend tests failed' }

    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Core npm ci failed' }
        npm test
        if ($LASTEXITCODE -ne 0) { throw 'Core React tests failed' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Core React build failed' }
    } finally { Pop-Location }
    & $python scripts/check_react_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Core build signature failed' }

    Push-Location business_frontend
    try {
        $env:VITE_API_BASE = '/business'
        $env:VITE_PRUVS_CUSTOMER_URL = ''
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Combined Business npm ci failed' }
        npm run build -- --base=/business/
        if ($LASTEXITCODE -ne 0) { throw 'Combined Business build failed' }
    } finally {
        Pop-Location
        Remove-Item Env:VITE_API_BASE, Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
    }
} finally { Pop-Location }

Push-Location (Join-Path $businessVerify 'backend')
try {
    py -3.12 -m venv .stagevenv
    if ($LASTEXITCODE -ne 0) { throw 'Business Python venv failed' }
    $python = Join-Path (Get-Location) '.stagevenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Business requirements failed' }
    & $python -m pytest -q tests/test_receipt_code_access_v0610.py tests/test_pilot_readiness_v069.py tests/test_wallet_legacy_v068.py tests/test_stage_schema_v066.py tests/test_stage_v067_business.py tests/test_serve_ui_v065.py
    if ($LASTEXITCODE -ne 0) { throw 'Business tests failed' }
} finally { Pop-Location }
Push-Location (Join-Path $businessVerify 'frontend')
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Independent Business npm ci failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Independent Business build failed' }
} finally { Pop-Location }

git -C $coreVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Core whitespace/patch issue' }
git -C $businessVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Business whitespace/patch issue' }
Write-Host 'Local verification commands completed successfully.' -ForegroundColor Green
```

The worktrees are **detached** and must not be used to push directly to `main`. Builds may update tracked `dist` files inside the isolated worktrees; never stage generated binaries or unrelated files without review.

### If a validation issue requires a source patch

Commit only to the intended *release branch* in a separate, clean branch worktree, not to production. Do not `git add .`, `git push --force`, `git reset --hard` or stage local backups, `.env`, virtualenvs, `node_modules`, `dist`, or credentials.

```powershell
# Example only: run inside a checked-out release branch with reviewed source edits.
git status --short
git add -- backend/business/pilot_v12.py backend/tests/test_receipt_code_access_v0610.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace issue' }
git diff --cached --stat
git diff --cached
# Confirm the staged changes are expected before:
# git commit -m "fix: staging code verification regression"
# git push origin HEAD
```

## Staging database gate (no automatic migrations)

Core and Business databases must remain distinct. The combined staging service uses `DATABASE_URL` for `pruvs_core_staging` and `BUSINESS_DATABASE_URL` for `pruvs_business_staging`. Do **not** use production credentials or copy connection strings into chat.

In the standalone Business backend using a securely loaded **staging-only** `DATABASE_URL`:

```powershell
Set-Location (Join-Path $businessVerify 'backend')
$python = Join-Path (Get-Location) '.stagevenv\Scripts\python.exe'
& $python -c "import os; from sqlalchemy.engine import make_url; u=make_url(os.environ['DATABASE_URL']); assert u.database=='pruvs_business_staging' and u.username=='pruvs_business_stage', 'STOP: wrong DB or role'; print('PASS: staging logical DB/role')"
if ($LASTEXITCODE -ne 0) { throw 'Unsafe DB connection. STOP.' }
& $python -m alembic current
if ($LASTEXITCODE -ne 0) { throw 'Alembic inspection failed. STOP.' }
& $python scripts/check_stage_schema_v066.py
# Exit 2 means migrations remain missing. It is not a successful check.
```

Before any migration, separately use correctly scoped staging PostgreSQL client credentials (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE), verify `SELECT current_database(), current_user`, and make a backup of exactly the staging logical database:

```powershell
$backup = Join-Path $root 'pruvs_business_staging_pre_v0610.dump'
pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=$backup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. STOP.' }
pg_restore --list $backup | Select-Object -First 10
if ($LASTEXITCODE -ne 0) { throw 'Backup verification failed. STOP.' }
Get-FileHash $backup -Algorithm SHA256
```

**Restoration must be tested to an isolated empty temporary staging database, never production.** Inspect the additive Business b08, b09 and b10 Alembic scripts; only after a verified restore test and confirmed exact staging database/role may the operator run `& $python -m alembic upgrade head`, and then `& $python scripts/check_stage_schema_v066.py`. Do not run automatic/destructive downgrades.

## Render staging only

Use the existing **Pruvs-staging** service on Render. Combined repo `MelinteB/Pruvio`, root `backend`, **Auto-Deploy OFF**, branch `release/pruvs-platform-v7154-b0610-combined-stage-20261113`. The combined ASGI service must have `PRUVS_PLATFORM_COMBINED_STAGING=true` and `CANONICAL_REDIRECT_ENABLED=false`. Keep both DB URLs and signing secrets separately configured; feature flags remain OFF until acceptance is complete.

Render Bash build command:

```bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_receipt_code_access_v0610.py tests/test_receipt_currency_v7153.py tests/test_pilot_readiness_v069.py tests/test_wallet_legacy_v068.py tests/test_combined_platform_routes.py
```

Start command:

```bash
exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port ${PORT:-10000}
```

Only after tests and the Business staging migration gate pass should a staging operator choose **Manual Deploy → Deploy latest commit**. Verify the Render-deployed commit equals the expected branch SHA. Do not alter the production service, `main`, production DB, or active secrets.

Read-only external smoke check after staging deployment:

```powershell
& (Join-Path $coreVerify 'scripts\Verify-Pruvs-Combined-Staging-v7154-b0610.ps1') -BaseUrl 'https://pruvs-core-staging.onrender.com' -RequireSchemaReady
```

## Acceptance tests

1. Core `/health` and `/api/v1/release` show **7.1.54**; Business `/business/health` shows **0.6.10**; updated React assets and PWA version are served.
2. Customer receipt remains visible if `/loyalty/claims` returns HTTP 503; no Generate button appears until status is verified. Historic receipt groups, split sessions and local receipt files remain untouched.
3. Customer submits with consent and sees a 20-minute code/QR without the modal closing prematurely; Business inbox shows **customer code needed** instead of a Review button.
4. Merchant enters code, reviews the consented preview, and can approve/reject only within the staff-specific 15-minute unlock period.
5. Customer reissues the pending code. The **old code fails lookup**; a prior preview view cannot authorize approval/rejection; merchant must use new code and view the receipt again.
6. Reissuing against altered evidence/amount must fail 409 without changing stored evidence. An unrelated merchant cannot look up the code or access the evidence.
7. After an approved claim, one stamp is awarded exactly once. Rewards are minted at the threshold and redeem only through the audited completed-sale reference flow; legacy confirmation remains blocked.
8. Verify both independent Business and combined Business source changes, then perform the user and merchant pilot using isolated staging identities and test receipts only.

## Rollback

Restore only the **previous staging** Core branch `release/pruvs-platform-v7153-b069-combined-stage-20261113` and Business branch `release/pruvs-business-v0.6.9-stage-20261113` with their known-good build/start settings. Keep the additive b08/b09/b10 schema and audit records; never automatically remove financial history.
