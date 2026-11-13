# Staging release: Pruvs Core v7.1.52 + Business v0.6.8

**STAGING ONLY. The candidate branches do not modify production, the active Render service, or the database.**

Combined GitHub repo: \`MelinteB/Pruvio\`
Combined branch: \`release/pruvs-platform-v7152-b068-combined-stage-20261113\`
Business GitHub repo: \`MelinteB/Pruvs-Business\`
Independent Business branch: \`release/pruvs-business-v0.6.8-stage-20261113\`
Combined rollback branch: \`release/pruvs-platform-v7151-b067-combined-stage-20261112\`

## What changed

- Core v7.1.52: Fix misleading "empty Wallet" after HTTP 503; show an unavailable state with manual retry instead.
- Core: Fetch joined program IDs from the new, independent \`/api/v1/loyalty/memberships\` route. When membership state cannot be verified, disable joining to avoid ambiguous duplicates. Keep saved Core receipts visible without requiring the reward ledger.
- Core: Promotions can be unavailable without disabling published loyalty programs. Show partial-outage status, not a blank screen.
- Core: A failed discount reconciliation request now displays a warning instead of "No redeemed discounts yet."
- Core: Refresh PWA service-worker URL to v7.1.52 to avoid stale frontend code after deployment.
- Business v0.6.8: Expose authenticated \`/v1/customer/memberships\` and make \`/v1/customer/wallet\` select only the legacy Reward columns needed for display. This avoids selecting \`loyalty_rewards.source_claim_id\` on the existing pre-b10 schema. No stamps, purchases, or rewards are created or changed by these read paths.
- Both: Regression tests exercise old database schemas without \`source_claim_id\`. Core frontend tests prove that failed Wallet requests never appear as an empty account.

**This is a compatibility update, not a substitute for database migration.** Business promotion publishing and discount reconciliation still need the additive migrations b08, b09 and b10. Do not tell customers that a merchant is asleep when a schema migration is incomplete.

## Predeployment validation in Windows PowerShell

Do not modify a working project folder. Start from the existing local Core Git repository and create a detached verification worktree:

\`\`\`powershell
$ErrorActionPreference = 'Stop'
$repo = Join-Path $HOME 'Personal\Project\Pruvs-Stage-UX-20261110'
$branch = 'release/pruvs-platform-v7152-b068-combined-stage-20261113'
$verify = Join-Path $HOME 'Personal\Project\Pruvs-v7152-Verification'
git -C $repo fetch origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
if (Test-Path $verify) { throw 'Verification worktree already exists; do not overwrite it' }
$sha = (git -C $repo rev-parse "origin/$branch").Trim()
git -C $repo worktree add --detach $verify $sha
if ($LASTEXITCODE -ne 0) { throw 'Worktree setup failed' }
$backend = Join-Path $verify 'backend'
Set-Location $backend
py -3.12 -m venv .stagevenv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
& .\.stagevenv\Scripts\python.exe -m pip install -r requirements.txt -r business-requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.stagevenv\Scripts\python.exe -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py tests/test_stage_v067.py tests/test_wallet_legacy_v068.py
if ($LASTEXITCODE -ne 0) { throw 'Backend validation failed' }
Push-Location frontend
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Core npm ci failed' }
npm test
if ($LASTEXITCODE -ne 0) { throw 'Core React tests failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Core build failed' }
Pop-Location
& .\.stagevenv\Scripts\python.exe scripts/check_react_build.py
if ($LASTEXITCODE -ne 0) { throw 'Core build verification failed' }
Push-Location business_frontend
$env:VITE_API_BASE = '/business'
$env:VITE_PRUVS_CUSTOMER_URL = ''
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Business npm ci failed' }
npm run build -- --base=/business/
if ($LASTEXITCODE -ne 0) { throw 'Business bundle failed' }
Pop-Location
Remove-Item Env:VITE_API_BASE,Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
git -C $verify status --short
\`\`\`

**No unrelated files should be staged or pushed.** Do not \`git add .\`, \`git push --force\`, or commit local node_modules, backup files, dist outputs, or venv. If a later authorized source patch needs publishing, stage specific paths with \`git add -- path/to/file1 path/to/file2\`, inspect \`git diff --cached --check\`, \`git diff --cached\`, then commit/push to the release branch only.

## Business staging database — read-only check and migration gate

Existing Business staging database name \`pruvs_business_staging\`; role \`pruvs_business_stage\`. Core data must remain in the separate \`pruvs_core_staging\` database. Never substitute production values.

The v0.6.8 Wallet read path tolerates the missing b10 \`source_claim_id\` column; **receipt reward redemption/reconciliation and campaign publishing still require all migrations**.

Before any migration, verify the exact connected logical database and role using \`SELECT current_database(),current_user\`. Back up the EXACT Business staging logical DB using correctly scoped staging credentials:

\`\`\`powershell
# Example after securely configuring staging-only PostgreSQL connection settings.
pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=pruvs_business_staging_pre_v068.dump
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. STOP.' }
pg_restore --list pruvs_business_staging_pre_v068.dump | Select-Object -First 10
if ($LASTEXITCODE -ne 0) { throw 'Backup archive check failed. STOP.' }
Get-FileHash .\pruvs_business_staging_pre_v068.dump -Algorithm SHA256
\`\`\`

Validate restoration to an isolated test database before migrating. Do not print credentials, copy database URLs into chat, or run against production. In the independent Business source branch (\`MelinteB/Pruvs-Business\`), \`backend\` directory and a safely loaded staging-only \`DATABASE_URL\`, inspect \`python -m alembic current\` and \`python scripts/check_stage_schema_v066.py\`. Review the additive b08, b09, and b10 migration scripts. ONLY AFTER the backup and migration review, and after confirming staging database/role, run \`python -m alembic upgrade head\` in that standalone Business environment. Re-run \`python scripts/check_stage_schema_v066.py\` and require all schema checks PASS. Never run automatic destructive downgrades.

## Render staging configuration

Use existing \`Pruvs-staging\` Render Web Service, repository \`MelinteB/Pruvio\`, root directory \`backend\`, Auto-Deploy OFF.

- **Branch:** \`release/pruvs-platform-v7152-b068-combined-stage-20261113\`
- **Core DB:** \`DATABASE_URL\` pointing at \`pruvs_core_staging\`.
- **Business DB:** \`BUSINESS_DATABASE_URL\` pointing at \`pruvs_business_staging\`.
- **Required staging secrets:** existing separate \`BUSINESS_JWT_SECRET\`, \`PRUVS_BRIDGE_SECRET\`. Never publish these values.
- **Combined service flags:** \`PRUVS_PLATFORM_COMBINED_STAGING=true\`, \`CANONICAL_REDIRECT_ENABLED=false\`.
- **Build command** (Render Bash):

\`\`\`bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py tests/test_stage_v067.py tests/test_wallet_legacy_v068.py
\`\`\`

- **Start command:** \`exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port \${PORT:-10000}\`

Do not change production services, the production branch, production environment variables, or the production database. Use **Manual Deploy → Deploy latest commit** only after checks. Confirm Render's deployed SHA matches the new branch HEAD.

## Release acceptance and manual test

The read-only release smoke script \`scripts/Verify-Pruvs-Combined-Staging-v7152-b068.ps1\` checks Core 7.1.52, Business 0.6.8, both frontends, public discovery, and optional Business schema readiness. \`/business/ready\` returning 503 requires a migration before pilot activation. Pass \`-RequireSchemaReady\` to make that a hard failure.

Then authenticate as a pilot Core customer in the browser:

1. **Discover:** previously joined program must be marked Joined even before the b10 migration; program membership comes from \`/api/v1/loyalty/memberships\`.
2. **Wallet:** pre-b10 membership and reward progress must display instead of HTTP 503. Simulate a temporary outage only in isolated tests; error must show a Retry control, not "No programs joined."
3. **Saved receipts:** Core-owned receipts remain visible when the Business membership route fails. Receipt claiming remains disabled until membership is verified.
4. **Campaigns:** a missing b08 media migration may yield unavailable campaigns, but published loyalty programs remain browseable. Do not publish campaigns until schema readiness passes.
5. **Redeem / reconcile:** require completed b08-b10 migrations, explicit customer consent, merchant receipt approval, single-use checkout code, completed merchant sale reference, and no duplicate credits or redemptions.
6. **Mobile:** validate the previously fixed floating '+' button and item swipes on Android portrait/landscape and iOS; PWA should fetch updated v7.1.52 assets.

## Rollback

Restore only the previous combined staging Render branch \`release/pruvs-platform-v7151-b067-combined-stage-20261112\` and the earlier known-good Build/Start settings. Additive b08/b09/b10 schema changes should remain unless a separate reviewed rollback plan requires otherwise; never remove financial audit tables automatically. Keep the independent Business staging resources for fallback. No production changes.
