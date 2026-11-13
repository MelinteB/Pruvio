# Pruvs Core v7.1.55 + Pruvs Business v0.6.11 — AI Campaign Journey

**STAGING ONLY — NOT LIVE, NOT TEST-SIGNED-OFF.** These are isolated release candidates. Creating the branches and source commits did not deploy to Render or change production settings, customer receipts or databases.

## Repositories, versions and rollback

| Component | Repository | Staging branch | Rollback branch |
|---|---|---|---|
| Core 7.1.55, combined Business 0.6.11 | MelinteB/Pruvio | `release/pruvs-platform-v7155-b0611-combined-stage-20261113` | `release/pruvs-platform-v7154-b0610-combined-stage-20261113` |
| Standalone Business 0.6.11 | MelinteB/Pruvs-Business | `release/pruvs-business-v0.6.11-stage-20261113` | `release/pruvs-business-v0.6.10-stage-20261113` |

API contracts remain v1. No destructive migrations, schema updates or merchant payment changes were made.

## Changes and identified defects

1. **Campaigns page now reaches the real AI Campaign Studio.** The obsolete template-only page and misleading "AI later" messaging no longer obstruct this route. Existing old template records are not deleted.
2. **Copy generation** uses the authenticated `POST /v1/merchant/promotions/ai-draft` route, structured JSON, server-side merchant/program facts, controlled error messages, and more output budget. No automatic publication or changes to loyalty terms.
3. **AI artwork**: new authenticated `POST /v1/merchant/promotions/ai-artwork`, using `gpt-image-2` by default (override via `PRUVS_CAMPAIGN_AI_IMAGE_MODEL`). Generates original artwork, validates/re-encodes to metadata-stripped JPEG, stores in merchant-scoped object storage, and returns private editing references plus approved public CDN URL. Only manager/owner of the published program can request it; separate explicit AI-image flag required.
4. **Branded formats**: the UI default format was invalid (`image`) while the renderer expects `png`, `gif`, `mp4`. It now defaults to `png`. The flow generates source artwork, renders a branded 4:5 PNG or a 3-second animated GIF/MP4 from the source, previews it, and then lets the merchant save and manually publish. GIF/MP4 requires the existing media renderer and ffmpeg dependency.
5. **Preflight readiness**: authenticated `GET /v1/merchant/promotions/ai-readiness` indicates AI text/artwork and campaign schema readiness. Both provider keys and the media migration are required before billable operations. AI budget and provider permissions still require external checks.
6. **Publication**: a promotion remains `draft` until owner/manager publishes; Business exposes only currently published, unexpired promotions for active merchant/store/published program. Pausing removes them from discovery. All lifecycle routes fail with controlled 503 when the media migration is missing.
7. **Customer app**: promotion card links directly to `/rewards?program=...` and highlights the associated loyalty program. A temporary campaign-service outage shows Retry instead of silently presenting a blank page. Existing verified-receipt, membership and reward flows remain independent.

## Required staging environment

Use only existing distinct Core and Business logical databases. Check and back up staging before migrating anything.

```text
PRUVS_PLATFORM_COMBINED_STAGING=true
CANONICAL_REDIRECT_ENABLED=false
DATABASE_URL=            # pruvs_core_staging, secure and private
BUSINESS_DATABASE_URL=   # pruvs_business_staging, secure and private
BUSINESS_JWT_SECRET=     # keep existing secret, do not print
PRUVS_BRIDGE_SECRET=     # keep existing distinct secret, do not print
VITE_PRUVS_LOYALTY_UI_ENABLED=true

PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED=true    # ONLY after staging preflight passes
PRUVS_BUSINESS_AI_IMAGES_ENABLED=true       # ONLY after staging preflight passes
OPENAI_API_KEY=                             # secret in Render, never in Git
PRUVS_CAMPAIGN_AI_MODEL=gpt-6-luna          # configurable copy model
PRUVS_CAMPAIGN_AI_IMAGE_MODEL=gpt-image-2   # configurable artwork model

PRUVS_CAMPAIGN_R2_ENDPOINT_URL=             # approved HTTPS S3-compatible endpoint
PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID=            # secret
PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY=        # secret
PRUVS_CAMPAIGN_R2_BUCKET=                   # dedicated campaign-media bucket
PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL=       # approved HTTPS CDN URL
PRUVS_CAMPAIGN_MEDIA_HOSTS=                 # comma-separated approved hostnames, not URLs
```

Do not print actual environment values, paste secrets into chat, enable AI in production, or expose internal object storage. Provider access, billing, available credits, project spending limits and CDN permissions must be validated separately. A ChatGPT subscription does not provision an API key or API credits.

## Windows PowerShell: copy-paste local verification

Git, Python 3.12, Node 22 and npm are required. Work only in isolated detached worktrees; do not overwrite existing working folders. If the candidate local Git sources are not at the known locations, set `$coreSource` or `$bizSource` to the actual local cloned repository before running.

```powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $HOME 'Personal\Project'
$coreSource = Join-Path $root 'Pruvs-Stage-UX-20261110'
$bizSource = Join-Path $root 'Pruvs-Business'
$coreBranch = 'release/pruvs-platform-v7155-b0611-combined-stage-20261113'
$bizBranch = 'release/pruvs-business-v0.6.11-stage-20261113'
$coreVerify = Join-Path $root 'Pruvs-Core-v7155-Verify'
$bizVerify = Join-Path $root 'Pruvs-Business-v0611-Verify'

foreach ($folder in @($coreSource,$bizSource)) {
    if (-not (Test-Path (Join-Path $folder '.git'))) {
        throw "Local Git clone not found: $folder. Update the source path; no files were overwritten."
    }
}
foreach ($folder in @($coreVerify,$bizVerify)) {
    if (Test-Path $folder) { throw "STOP: verification worktree already exists: $folder" }
}
if ((git -C $coreSource remote get-url origin) -notmatch 'MelinteB/Pruvio(\.git)?$') {
    throw 'Wrong Core origin. STOP.'
}
if ((git -C $bizSource remote get-url origin) -notmatch 'MelinteB/Pruvs-Business(\.git)?$') {
    throw 'Wrong Business origin. STOP.'
}
git -C $coreSource fetch origin $coreBranch
if ($LASTEXITCODE -ne 0) { throw 'Core fetch failed' }
git -C $bizSource fetch origin $bizBranch
if ($LASTEXITCODE -ne 0) { throw 'Business fetch failed' }

$coreSha = (git -C $coreSource rev-parse "origin/$coreBranch").Trim()
$bizSha = (git -C $bizSource rev-parse "origin/$bizBranch").Trim()
git -C $coreSource worktree add --detach $coreVerify $coreSha
if ($LASTEXITCODE -ne 0) { throw 'Core worktree failed' }
git -C $bizSource worktree add --detach $bizVerify $bizSha
if ($LASTEXITCODE -ne 0) { throw 'Business worktree failed' }
Write-Host "Core candidate SHA: $coreSha" -ForegroundColor Cyan
Write-Host "Business candidate SHA: $bizSha" -ForegroundColor Cyan

Push-Location (Join-Path $coreVerify 'backend')
try {
    py -3.12 -m venv .verifyvenv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
    $python = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt -r business-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Combined dependencies failed' }
    & $python -m compileall -q business app/react_app/loyalty_api.py
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax failed' }
    & $python -m pytest -q tests/test_campaign_journey_v0611.py tests/test_receipt_currency_v7153.py tests/test_wallet_legacy_v068.py tests/test_pilot_readiness_v069.py tests/test_receipt_code_access_v0610.py tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py
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
    if ($LASTEXITCODE -ne 0) { throw 'Core release signature mismatch' }
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
        Remove-Item Env:VITE_API_BASE,Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
    }
} finally { Pop-Location }

Push-Location (Join-Path $bizVerify 'backend')
try {
    py -3.12 -m venv .verifyvenv
    if ($LASTEXITCODE -ne 0) { throw 'Business Python environment failed' }
    $python = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Business dependencies failed' }
    & $python -m pytest -q tests/test_campaign_journey_v0611.py tests/test_stage_v067_business.py tests/test_stage_schema_v066.py tests/test_pilot_readiness_v069.py tests/test_receipt_code_access_v0610.py
    if ($LASTEXITCODE -ne 0) { throw 'Business backend tests failed' }
} finally { Pop-Location }
Push-Location (Join-Path $bizVerify 'frontend')
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Business npm ci failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Business React build failed' }
} finally { Pop-Location }

git -C $coreVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Core diff issue' }
git -C $bizVerify diff --check
if ($LASTEXITCODE -ne 0) { throw 'Business diff issue' }
Write-Host 'LOCAL VALIDATION COMMANDS COMPLETED' -ForegroundColor Green
```

These commands do not deploy or migrate. Generated files may appear in the detached worktrees; do not stage them blindly.

### Selective source patch staging, if validation fails

Apply reviewed source fixes to the **release branch**, not `main`. Never `git add .` or force-push; never stage secrets, backups, virtualenvs, `dist` or `node_modules`.

```powershell
# Example only: execute inside a checked-out staging RELEASE branch worktree.
git status --short
git add -- backend/business/ai_campaign_artwork_v0611.py backend/tests/test_campaign_journey_v0611.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged patch failed whitespace checks' }
git diff --cached --stat
git diff --cached
# Inspect all changes before any authorized commit/push.
# git commit -m "fix: AI campaign staging validation"
# git push origin HEAD
```

## Business STAGING database gate

Before enabling campaigns, confirm the **exact** Business staging logical database and role; Core must remain in its distinct database.

```powershell
# In the standalone Business verification backend.
Set-Location (Join-Path $bizVerify 'backend')
$python = Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
# DATABASE_URL must be loaded securely with Business STAGING credentials before these commands.
& $python -c "import os; from sqlalchemy.engine import make_url; u=make_url(os.environ['DATABASE_URL']); assert u.database=='pruvs_business_staging' and u.username=='pruvs_business_stage', 'WRONG TARGET'; print('PASS: staging logical database and role')"
if ($LASTEXITCODE -ne 0) { throw 'Unsafe Business DB target. STOP.' }
& $python -m alembic current
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Business Alembic revision. STOP.' }
& $python scripts/check_stage_schema_v066.py
# Any nonzero exit means readiness is INCOMPLETE, not that migrations succeeded.
```

Take and restore-test a staging-only logical backup before any migration. Use separate secure staging-only PostgreSQL client connection variables; verify `SELECT current_database(),current_user` in the database and inspect b08/b09/b10 Alembic scripts first.

```powershell
$backup = Join-Path $root 'pruvs_business_staging_pre_v0611.dump'
pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=$backup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. STOP.' }
pg_restore --list $backup | Select-Object -First 10
if ($LASTEXITCODE -ne 0) { throw 'Archive could not be checked. STOP.' }
Get-FileHash $backup -Algorithm SHA256
# Restore-test to a separate empty staging-only database before migrations.
# ONLY after verified target, backup, restore-test and migration review:
# & $python -m alembic upgrade head
# & $python scripts/check_stage_schema_v066.py
```

Never run automatic destructive downgrades or mutate production databases. B08 campaign-media migration is the minimum AI campaign gate; the full receipt-to-reward pilot also needs b09/b10.

## Render STAGING manual deployment

Only after tests and DB readiness are verified:
- Service: existing `Pruvs-staging` web service.
- GitHub repository: `MelinteB/Pruvio`.
- Root: `backend`.
- Auto-deploy: **OFF**.
- Branch: `release/pruvs-platform-v7155-b0611-combined-stage-20261113`.
- Existing Core/Business staging secrets and DBs stay separate.
- Do not enable AI flags until CDN/provider limits and readiness checks pass.

Render Bash build:

```bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_campaign_journey_v0611.py tests/test_wallet_legacy_v068.py tests/test_stage_schema_v066.py
```

Render Bash start:

```bash
exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port ${PORT:-10000}
```

Use **Manual Deploy → Deploy latest commit** on STAGING only. Verify the Render deployed SHA against `$coreSha`. Execute the read-only smoke check once the staging schema is ready:

```powershell
& (Join-Path $coreVerify 'scripts\Verify-Pruvs-Combined-Staging-v7155-b0611.ps1') -BaseUrl 'https://pruvs-core-staging.onrender.com' -RequireSchemaReady
```

## Browser + API acceptance matrix — REQUIRED before "fully functional"

All tests must use *isolated staging merchants, customer accounts, receipts and API credentials*. Do not use live customer financial data or production POS connections.

1. **Merchant setup:** sign in as owner, create/confirm an active store and publish a loyalty program. Check current eligibility (e.g., number of stamps, min purchase, amount and currency).
2. **Readiness:** open Business → AI campaign studio. Check `GET /business/v1/merchant/promotions/ai-readiness` authenticated. Require `copy_ready=true`, `artwork_ready=true`, `campaign_schema_ready=true` before starting.
3. **AI copy:** choose program, set audience/tone/goal, generate. The returned text must reflect *only the real program terms*, be editable by merchant, and have no hallucinated discount/POS integration.
4. **AI media:** generate image, then render default PNG; verify approved HTTPS CDN, correct 4:5 preview and watermark. Also check GIF and MP4 if those format options will be enabled for merchants; MP4 depends on ffmpeg availability.
5. **Save draft:** confirm merchant database has one draft with program linkage and media; `GET /business/v1/promotions` must NOT reveal it. Deliberately stop and review before publishing.
6. **Publish:** click Publish; `GET /business/v1/promotions` must show only eligible public campaigns, and Core Discover/Home must render the approved creative. Click "See loyalty program" and confirm the matching program appears first.
7. **Join and earn:** sign in to a pilot customer, join published program, scan and submit an eligible consented receipt with verified purchase claim code. Merchant approves, one stamp is earned, progress appears in Wallet. Redemption is possible only when threshold is met and after a completed merchant sale reference, subject to b09/b10.
8. **Unpublish:** merchant unpublishes; public Pruvs campaign disappears while the underlying published loyalty program and accumulated customer progress remain intact.
9. **Failure paths:** no API key, insufficient credit, provider 429/5xx, failed image storage, unapproved CDN, missing b08, non-owner merchant, draft/unpublished program, expired campaign, inactive store; expect controlled error and **no automatic publish, stamp credit, or POS action**.
10. **Mobile:** inspect actual iOS and Android campaign preview, AI dialog, GIF and MP4 autoplay constraints, responsive card and PWA asset updates.

An automated test suite cannot prove provider billing, Render configurations, CDN access or browser media support. Mark these manually verified only after testing the staging deployment.

## Rollback

Switch the **staging** Render service to the prior combined `release/pruvs-platform-v7154-b0610-combined-stage-20261113` branch and matching known-good build/start settings. Standalone Business reverts to `release/pruvs-business-v0.6.10-stage-20261113`. Leave additive schema changes and financial audit records intact; disable the new AI-image flag if provider/media faults occur. Production remains untouched.
