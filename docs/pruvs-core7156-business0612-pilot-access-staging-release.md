# Pruvs Core 7.1.56 + Business 0.6.12 — Staging Release

STAGING CANDIDATE. Source is committed in GitHub; the b11 migration, tests, Render deployment and production changes were NOT performed as part of preparing these branches.

Core + combined Business repository: MelinteB/Pruvio
Branch: release/pruvs-platform-v7156-b0612-combined-stage-20261113
Standalone Business repository: MelinteB/Pruvs-Business
Branch: release/pruvs-business-v0.6.12-stage-20261113
Rollback: combined v7.1.55/B0.6.11, standalone B0.6.11 staging branches.

## What changes

Business is the single source of truth for merchant identity, loyalty pilot permissions and decision history. Core receives read-only merchant_id and receipt_pilot_allowed on the existing discovery API. Core cannot grant access by passing a merchant ID. An absent Business eligibility field fails closed for receipt claiming but not for browsing or joining programs.

New Business b11 additive migration creates merchant_pilot_enrollment_v0612 and merchant_pilot_audit_v0612. All new merchants begin unapproved. Business owner/manager can request access after publishing an eligible program. Only a dedicated platform_admin staff role, provisioned offline by an authorized staging operator, may approve, deny or revoke requests in the Business Pilot access screen. Decisions are audited. The merchant active status is not independent KYC verification; the operator must separately review the business.

The feature is OFF by default. With PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=true, Business ignores the old static PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS. Keep that old variable available until the transition is validated for rollback. DB mode requires consented receipt evidence and blocks legacy direct claiming. Existing memberships, accrued stamps and audit records are retained on revocation.

## Full Windows PowerShell: isolated backend and UI verification

Requirements: Git, Python 3.12, Node.js 22, npm. Before using these commands, point $coreSource and $businessSource to your existing correct local clones; never overwrite an existing working tree.

~~~powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $HOME 'Personal\Project'
$coreSource = Join-Path $root 'Pruvs'
$businessSource = Join-Path $root 'Pruvs-Business'
$coreBranch = 'release/pruvs-platform-v7156-b0612-combined-stage-20261113'
$businessBranch = 'release/pruvs-business-v0.6.12-stage-20261113'
$coreVerify = Join-Path $root 'Pruvs-Core-v7156-Verify'
$businessVerify = Join-Path $root 'Pruvs-Business-v0612-Verify'
if (-not (Test-Path (Join-Path $coreSource '.git'))) { throw 'Core clone missing: correct $coreSource and retry' }
if (-not (Test-Path (Join-Path $businessSource '.git'))) { throw 'Business clone missing: correct $businessSource and retry' }
if ((git -C $coreSource remote get-url origin) -notmatch 'MelinteB/Pruvio(\.git)?$') { throw 'Unexpected Core origin' }
if ((git -C $businessSource remote get-url origin) -notmatch 'MelinteB/Pruvs-Business(\.git)?$') { throw 'Unexpected Business origin' }
if ((Test-Path $coreVerify) -or (Test-Path $businessVerify)) { throw 'Refusing to overwrite an existing verification directory' }
git -C $coreSource fetch origin $coreBranch
if ($LASTEXITCODE -ne 0) { throw 'Core fetch failed' }
git -C $businessSource fetch origin $businessBranch
if ($LASTEXITCODE -ne 0) { throw 'Business fetch failed' }
$coreSha = (git -C $coreSource rev-parse "origin/$coreBranch").Trim()
$businessSha = (git -C $businessSource rev-parse "origin/$businessBranch").Trim()
git -C $coreSource worktree add --detach $coreVerify $coreSha
if ($LASTEXITCODE -ne 0) { throw 'Core isolated worktree creation failed' }
git -C $businessSource worktree add --detach $businessVerify $businessSha
if ($LASTEXITCODE -ne 0) { throw 'Business isolated worktree creation failed' }
Write-Host "Core candidate: $coreSha"
Write-Host "Business candidate: $businessSha"

Push-Location (Join-Path $coreVerify 'backend')
try {
  py -3.12 -m venv .verifyvenv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 required' }
  $py = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
  & $py -m pip install -r requirements.txt -r business-requirements.txt
  if ($LASTEXITCODE -ne 0) { throw 'Core/Business requirements failed' }
  & $py -m compileall -q business business_migrations
  if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed' }
  & $py -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_receipt_code_access_v0610.py tests/test_pilot_readiness_v069.py tests/test_campaign_journey_v0611.py tests/test_combined_platform_routes.py tests/test_wallet_legacy_v068.py tests/test_stage_schema_v066.py
  if ($LASTEXITCODE -ne 0) { throw 'Combined backend regression tests failed' }
  Push-Location frontend
  try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Core npm install failed' }
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Core React tests failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Core React build failed' }
  } finally { Pop-Location }
  & $py scripts/check_react_build.py
  if ($LASTEXITCODE -ne 0) { throw 'Core release signature failed' }
  Push-Location business_frontend
  try {
    $env:VITE_API_BASE = '/business'
    $env:VITE_PRUVS_CUSTOMER_URL = ''
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Combined Business npm install failed' }
    npm run build -- --base=/business/
    if ($LASTEXITCODE -ne 0) { throw 'Combined Business build failed' }
  } finally {
    Pop-Location
    Remove-Item Env:VITE_API_BASE, Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
  }
} finally { Pop-Location }

Push-Location (Join-Path $businessVerify 'backend')
try {
  py -3.12 -m venv .verifyvenv
  if ($LASTEXITCODE -ne 0) { throw 'Business Python environment failed' }
  $py = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
  & $py -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) { throw 'Business requirements failed' }
  & $py -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_receipt_code_access_v0610.py tests/test_pilot_readiness_v069.py tests/test_campaign_journey_v0611.py tests/test_wallet_legacy_v068.py
  if ($LASTEXITCODE -ne 0) { throw 'Independent Business tests failed' }
} finally { Pop-Location }
Push-Location (Join-Path $businessVerify 'frontend')
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw 'Business npm ci failed' }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'Business React build failed' }
} finally { Pop-Location }
git -C $coreVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Core patch whitespace check failed' }
git -C $businessVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Business patch whitespace check failed' }
Write-Host 'Local validation commands finished successfully.' -ForegroundColor Green
~~~

These worktrees are detached and should not push directly. If a source correction is needed, checkout the release branch in a separate clean worktree, stage only reviewed source paths and inspect the complete staged diff:

~~~powershell
git status --short
git add -- backend/business/pilot_enrollment_v0612.py backend/tests/test_pilot_enrollment_v0612.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed' }
git diff --cached --stat
git diff --cached
# Only after review, on the intended staging branch:
# git commit -m "fix: staging pilot enrollment regression"
# git push origin HEAD
~~~

Never git add .; never force push; never stage .env, backups, credentials, .verifyvenv, node_modules or generated dist without review.

## Explicit STAGING-only b11 database gate and backup

The Business DB must be pruvs_business_staging with role pruvs_business_stage, separate from pruvs_core_staging. Load its DATABASE_URL securely into a private PowerShell session. Do not print or share connection strings.

~~~powershell
Set-Location (Join-Path $businessVerify 'backend')
$py = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
& $py -c "import os; from sqlalchemy.engine import make_url; u=make_url(os.environ['DATABASE_URL']); assert u.database=='pruvs_business_staging' and u.username=='pruvs_business_stage', 'WRONG DATABASE/ROLE'; print('PASS: Business staging DB')"
if ($LASTEXITCODE -ne 0) { throw 'Wrong database/role — STOP' }
& $py -m alembic current
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Alembic — STOP' }
& $py scripts/check_stage_schema_v066.py
# If the earlier b08/b09/b10 gate fails, stop and investigate before b11.
~~~

Before any migration: set private PGHOST, PGPORT, PGUSER, PGPASSWORD and PGDATABASE for the same staging logical DB; verify SELECT current_database(),current_user in that connection; inspect the b11 script; create a backup and restore-test it into a separate empty staging database.

~~~powershell
$backup = Join-Path $root 'pruvs_business_staging_before_b11.dump'
pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=$backup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed — STOP' }
pg_restore --list $backup | Select-Object -First 10
if ($LASTEXITCODE -ne 0) { throw 'Archive inspection failed — STOP' }
Get-FileHash $backup -Algorithm SHA256
# Only after restore testing and exact database confirmation:
# & $py -m alembic upgrade head
# if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
~~~

Migration b11 creates the two new tables. It never auto-approves merchants and the downgrade intentionally refuses to delete audit history. Do not change production DBs.

## One-time dedicated staging platform operator

After b11: use the independent Business backend with the verified staging DATABASE_URL. The provisioning script checks exact logical database/role, asks for a new 20+ character password without echo and requires typed confirmation. It refuses to promote an existing merchant account.

~~~powershell
Set-Location (Join-Path $businessVerify 'backend')
$py = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
& $py scripts/provision_staging_pilot_admin_v0612.py --email 'REPLACE-WITH-DEDICATED-STAGING-OPERATOR-EMAIL' --confirm-staging
if ($LASTEXITCODE -ne 0) { throw 'Platform admin was not provisioned — STOP' }
& $py scripts/check_stage_pilot_schema_v0612.py
if ($LASTEXITCODE -ne 0) { throw 'Pilot schema/operator check failed — STOP' }
~~~

Store the operator password in a password manager. Do not commit it. The existing Business merchant login still requires rate limiting and stronger operator controls before production.

## Render STAGING release

Service: Pruvs-staging, repo MelinteB/Pruvio, root backend, branch release/pruvs-platform-v7156-b0612-combined-stage-20261113, Auto-Deploy OFF.

Keep the new flag false until backend tests and the b11/operator gate pass:

~~~dotenv
PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=false
~~~

Use the existing combined start command. The staging build can be tightened to run all relevant backend and frontend tests before activation:

~~~bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm test && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_receipt_code_access_v0610.py tests/test_pilot_readiness_v069.py tests/test_combined_platform_routes.py
~~~

~~~bash
exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port $PORT
~~~

Only after manual STAGING deploy, build/tests success and verified b11/operator readiness, set the flag to true on STAGING. In this mode the static merchant ID allowlist is ignored and the Business DB makes access decisions. Keep the old allowlist unchanged until rollback testing is completed.

~~~dotenv
PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=true
~~~

## Browser acceptance and read-only smoke

1. Verify Core /health = 7.1.56 and Business /business/health = 0.6.12, and that the deployed commit matches the intended combined branch.
2. Merchant owner with an active store/published program opens Business → Pilot access. Status starts not_requested. Click Request.
3. Status becomes requested. A regular merchant account receives 403 from platform-admin endpoints.
4. Dedicated platform operator logs in and approves. Audit history records the operator and transition. Core /api/v1/loyalty/offers now returns receipt_pilot_allowed=true for that merchant.
5. An unapproved merchant remains discoverable for loyalty program browsing/joining but cannot generate a customer receipt code.
6. Approved merchant can receive an explicitly consented receipt via the Core customer app, check its single-use code and approve it. One stamp is credited; duplicates are blocked.
7. Platform admin revokes. New receipt claims fail, Core read-only eligibility changes to false, existing memberships/stamps/history remain intact.
8. Deny requires a reason; after denial/revocation a merchant may request again. Neither a merchant owner nor Core can self-approve.
9. With b11 absent and DB mode on, requests must fail closed. With DB mode off, old static allowlist applies for rollback.

Read-only smoke, optionally supplying a short-lived staging merchant token from a secure shell:

~~~powershell
$smoke = Join-Path $coreVerify 'scripts\Verify-Pruvs-Pilot-Enrollment-Staging-v7156-b0612.ps1'
& $smoke -BaseUrl 'https://pruvs-core-staging.onrender.com'
# Securely load PRUVS_BUSINESS_STAGING_TOKEN using the staging merchant login if desired.
& $smoke -BaseUrl 'https://pruvs-core-staging.onrender.com' -RequireDatabaseMode -ExpectedMerchantStatus approved
if (-not $?) { throw 'Pilot acceptance smoke failed' }
Remove-Item Env:PRUVS_BUSINESS_STAGING_TOKEN -ErrorAction SilentlyContinue
~~~

Do not claim readiness until local tests, DB migration, operator provisioning, Render deployment and the complete merchant/customer/browser tests have passed.

## Rollback

Disable PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED on staging to restore the legacy allowlist behavior. If a code rollback is needed, restore the previous known-good combined staging branch v7.1.55/Business v0.6.11. Keep b11 tables and audit history; do not run a destructive downgrade. Production remains unchanged.
