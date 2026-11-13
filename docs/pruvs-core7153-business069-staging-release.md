# STAGING RELEASE — Pruvs Core v7.1.53 and Pruvs Business v0.6.9

**No production deployment has been authorized.** This is an additive code-only staging candidate. It does not migrate databases or enable pilot flags.

- Combined Core + Business repository: `MelinteB/Pruvio`
- Staging branch: `release/pruvs-platform-v7153-b069-combined-stage-20261113`
- Independent Business repository: `MelinteB/Pruvs-Business`
- Independent branch: `release/pruvs-business-v0.6.9-stage-20261113`
- Core rollback candidate: `release/pruvs-platform-v7152-b068-combined-stage-20261113`
- Business rollback candidate: `release/pruvs-business-v0.6.8-stage-20261113`

## Changes

**Core v7.1.53**
- Recognizes the exact receipt OCR alias `LEI` (case-insensitive) as ISO `RON`, without conversion or changed monetary amounts.
- Unknown or unsupported OCR values remain unconfirmed, allowing the receipt owner to select an ISO currency.
- Persists a canonical `RON` when an existing receipt contains the `LEI` alias, while retaining idempotency and refusing changes after a split exists or when a different valid currency is already set.
- Adds isolated tests for RON, LEI, EUR, USD, MDL, blank, unsupported and split-protected cases.
- Updates API release, browser release banner, frontend manifest, PWA registration URL and service-worker cache key to 7.1.53.

**Business v0.6.9**
- Adds authenticated, read-only `GET /v1/merchant/receipt-pilot/readiness`: merchant-scoped pilot permissions and database migration readiness, no secrets, no database mutation.
- Merchant receipt inbox shows clear blockers instead of implying that no receipts exist when setup is incomplete.
- Fails reward approval, reservation, and audited confirmation with controlled HTTP 503 before writes when the additive discount-reconciliation schema is missing.
- Disables legacy direct reward confirmation with HTTP 409; the supported path `/v1/merchant/redemptions/confirm` requires a completed sale reference and writes the audit ledger.
- Adds isolated regression tests of readiness and fail-closed behavior.
- Remains compatible with Core v7.1.52 for read-only operations while the pilot is off. No new destructive migration.

**Known gating issue:** Business staging still requires *verified staging-only* additive Alembic migrations b08 (campaign media), b09 (customer receipt codes), and b10 (reward reconciliation) before the full receipt-to-reward and redemption cycle can be enabled. A code update cannot repair missing DB tables.

## Windows PowerShell — verify the code, without modifying production

Use PowerShell 7+, Python 3.12, Node 22 and npm. The known local Core repository is `$HOME\Personal\Project\Pruvs-Stage-UX-20261110`; change that variable if the repository is elsewhere. Existing working directories must not be overwritten.

```powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $HOME 'Personal\Project'
$coreSource = Join-Path $root 'Pruvs-Stage-UX-20261110'
$businessSource = Join-Path $root 'Pruvs-Business'
$coreBranch = 'release/pruvs-platform-v7153-b069-combined-stage-20261113'
$businessBranch = 'release/pruvs-business-v0.6.9-stage-20261113'
$coreVerify = Join-Path $root 'Pruvs-v7153-Verification'
$businessVerify = Join-Path $root 'Pruvs-Business-v069-Verification'
foreach ($path in @($coreSource,$businessSource)) {
    if (-not (Test-Path (Join-Path $path '.git'))) {
        # Git worktrees may use a .git file instead of a directory; Test-Path supports both.
        throw "Missing local Git repository: $path"
    }
}
foreach ($path in @($coreVerify,$businessVerify)) {
    if (Test-Path $path) { throw "Existing verification folder; refusing overwrite: $path" }
}
git -C $coreSource fetch origin $coreBranch
if ($LASTEXITCODE -ne 0) { throw 'Core fetch failed' }
git -C $businessSource fetch origin $businessBranch
if ($LASTEXITCODE -ne 0) { throw 'Business fetch failed' }
$coreHead = (git -C $coreSource rev-parse "origin/$coreBranch").Trim()
$businessHead = (git -C $businessSource rev-parse "origin/$businessBranch").Trim()
git -C $coreSource worktree add --detach $coreVerify $coreHead
if ($LASTEXITCODE -ne 0) { throw 'Core worktree creation failed' }
git -C $businessSource worktree add --detach $businessVerify $businessHead
if ($LASTEXITCODE -ne 0) { throw 'Business worktree creation failed' }

Push-Location (Join-Path $coreVerify 'backend')
try {
    py -3.12 -m venv .stagevenv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment failed' }
    $python = Join-Path (Get-Location) '.stagevenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt -r business-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Core dependencies failed' }
    & $python -m pytest -q tests/test_receipt_currency_v7153.py tests/test_pilot_readiness_v069.py tests/test_wallet_legacy_v068.py tests/test_combined_platform_routes.py tests/test_stage_v067.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py
    if ($LASTEXITCODE -ne 0) { throw 'Core/Business backend tests failed' }
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
        if ($LASTEXITCODE -ne 0) { throw 'Business npm ci failed' }
        npm run build -- --base=/business/
        if ($LASTEXITCODE -ne 0) { throw 'Business frontend failed' }
    } finally {
        Pop-Location
        Remove-Item Env:VITE_API_BASE,Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
    }
} finally { Pop-Location }

Push-Location (Join-Path $businessVerify 'backend')
try {
    py -3.12 -m venv .stagevenv
    if ($LASTEXITCODE -ne 0) { throw 'Business Python environment failed' }
    $python = Join-Path (Get-Location) '.stagevenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Business dependencies failed' }
    & $python -m pytest -q tests/test_stage_schema_v066.py tests/test_stage_v067_business.py tests/test_wallet_legacy_v068.py tests/test_pilot_readiness_v069.py tests/test_serve_ui_v065.py
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Business tests failed' }
} finally { Pop-Location }
Push-Location (Join-Path $businessVerify 'frontend')
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Business npm ci failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Business build failed' }
} finally { Pop-Location }
git -C $coreVerify status --short
git -C $businessVerify status --short
Write-Host "STAGING CODE CHECKS COMPLETE. Core $coreHead / Business $businessHead" -ForegroundColor Cyan
```

Never use `git add .`, `git push --force` or stage local `dist`, backups, `node_modules`, virtualenvs or credentials. If a source patch is subsequently needed, stage *specific file paths* in an appropriate release worktree: `git add -- path/to/file1 path/to/file2`; inspect `git diff --cached --check` and `git diff --cached` before committing and pushing **only the release branch**.

## Database migration gate — Business STAGING ONLY

The combined service must have distinct `DATABASE_URL` pointing to `pruvs_core_staging` and `BUSINESS_DATABASE_URL` pointing to `pruvs_business_staging`; never reuse production URLs. The independent Business staging DB role must be `pruvs_business_stage`. In the independent Business backend folder, check the *live* connection target and the Alembic revision before any change:

```powershell
# First load the staging-only DATABASE_URL securely in this PowerShell session.
$backend = Join-Path $businessVerify 'backend'
Set-Location $backend
$python = Join-Path $backend '.stagevenv\Scripts\python.exe'
& $python -c "import os; from sqlalchemy.engine import make_url; u=make_url(os.environ['DATABASE_URL']); assert u.database=='pruvs_business_staging' and u.username=='pruvs_business_stage', 'STOP: wrong DB or role'; print('PASS: staging-only DB target and role')"
if ($LASTEXITCODE -ne 0) { throw 'Unsafe database target. STOP.' }
& $python -m alembic current
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Alembic revision. STOP.' }
& $python scripts/check_stage_schema_v066.py
# Exit 2 means migration is pending. DO NOT interpret this as a successful migration.
```

Before migration, obtain a *restorable* logical backup of that **exact staging DB**, verify its archive and restore into a separate temporary test database. Example after configuring secure staging-only PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE environment variables, never on a production shell:

```powershell
$backup = Join-Path $root 'pruvs_business_staging_pre_v069.dump'
pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=$backup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. STOP.' }
pg_restore --list $backup | Select-Object -First 10
if ($LASTEXITCODE -ne 0) { throw 'Backup unreadable. STOP.' }
Get-FileHash $backup -Algorithm SHA256
# Restore-test the dump to an isolated temporary DB and review b08/b09/b10.
# Only after the exact target, verified backup, restore test and migration review:
# & $python -m alembic upgrade head
# & $python scripts/check_stage_schema_v066.py
```

Never automate a destructive downgrade or run migration against production.

## Staging Render rollout

Render service: **Pruvs-staging**, repo `MelinteB/Pruvio`, root `backend`, Auto-Deploy **OFF**. Keep `PRUVS_PLATFORM_COMBINED_STAGING=true` and `CANONICAL_REDIRECT_ENABLED=false` only in staging; use existing distinct Core/Business credentials and database variables. Do not modify the production branch, service or database.

Manual deployment can proceed only after isolated tests and backup/migration gates:
- Render staging branch: `release/pruvs-platform-v7153-b069-combined-stage-20261113`
- Start command: `exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port ${PORT:-10000}`
- Build command: `pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_receipt_currency_v7153.py tests/test_pilot_readiness_v069.py tests/test_wallet_legacy_v068.py tests/test_combined_platform_routes.py`

Use **Manual Deploy → Deploy latest commit** on the **staging** service, and confirm the deployed SHA matches the verified release branch. Run the read-only `scripts/Verify-Pruvs-Combined-Staging-v7153-b069.ps1 -RequireSchemaReady` smoke check after migrating (omit the switch to inspect a not-yet-migrated staging service without claiming readiness).

## Acceptance criteria

1. LEI, lei and RON receipts can be saved as RON and start a split without changing monetary amounts; unknown currencies require explicit owner selection, while receipts with an existing split cannot be altered.
2. Both version health responses match Core 7.1.53 and Business 0.6.9; PWA service worker updates without purging saved local receipts.
3. Merchant `receipt-pilot/readiness` gives explicit blockers until flags and b08/b09/b10 are ready; no secrets are returned.
4. A customer with an eligible verified receipt can generate a single-use claim code (pilot only), merchant unlocks and inspects *consented* evidence and approves/rejects it; only approval adds one stamp.
5. On reaching the threshold, a reward is recorded exactly once; merchant redemption requires a completed sale reference, writes one reconciliation event, and repeated confirmation is rejected.
6. Old direct reward confirmation returns 409, without changing a reward.
7. Verify all actions in isolated staging with separate Core/Business accounts, never production users or customer receipts.

**Rollback:** Restore only the v7.1.52/v0.6.8 **staging branches** and known-good staging Build/Start settings. Do not automatically reverse b08/b09/b10 or delete audit ledger tables.
