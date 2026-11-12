# Pruvs Core v7.1.51 + Business v0.6.7 — combined staging release

STAGING ONLY. Both source branches exist. The live Render service and database have not been altered by these release preparations.

Combined repository: MelinteB/Pruvio
Release branch: release/pruvs-platform-v7151-b067-combined-stage-20261112
Independent Business repository: MelinteB/Pruvs-Business
Independent Business release branch: release/pruvs-business-v0.6.7-stage-20261112
Combined rollback branch: release/pruvs-platform-v7150-b066-combined-stage-20261112

## Functional scope

Core: hide archived or removed receipts/splits in project selection, enforce the same rule in server-side item add, whole-card swipe to change quantity, 650ms hold selects half, 1500ms selects all, successive double-taps halve/clear selection; customer receipt-claim code QR; wallet voucher QR; merchant-confirmed discount reconciliation.

Business: separate green favicon and brand, merchant loyalty program edit/publish/pause/resume, restricted customer program leave, OpenAI-generated copy reviewed against published reward criteria, authorized image upload, branded vertical image/GIF/MP4 outputs, merchant checkout sale reference, reconciliation CSV and discount ledger.

Existing receipt claim v1.2 verifies customer membership and receipt with consent. Merchant must unlock the claim with customer code, inspect the receipt image, then explicitly approve before stamps accrue. Reward QR is created only after enough verified purchases. No POS charge or bank settlement takes place inside Pruvs.

## Safety gates before deployment

1. Confirm both GitHub release checks PASS. Keep draft PRs unmerged until validation.
2. Confirm Core DATABASE_URL points to pruvs_core_staging and Business BUSINESS_DATABASE_URL points to pruvs_business_staging. Never substitute production credentials.
3. Create a restorable backup of the EXACT pruvs_business_staging logical database (not only a different database on the same Postgres instance). Using PostgreSQL client tools with staging credentials, verify SELECT current_database(), current_user first. Example after PGHOST/PGUSER/PGPASSWORD are set securely:

    pg_dump --format=custom --no-owner --no-acl --dbname=pruvs_business_staging --file=pruvs_business_staging_pre_v067.dump
    pg_restore --list pruvs_business_staging_pre_v067.dump
    Get-FileHash .\pruvs_business_staging_pre_v067.dump -Algorithm SHA256

Do NOT continue if backup or restore-list verification fails. Do not paste passwords in chat or commit backups.

4. In the independent Business v0.6.7 repository backend directory, with staging-only DATABASE_URL and secrets loaded securely, inspect:

    python -m alembic current
    python scripts/check_stage_schema_v066.py

Missing schema may exit 2 before migration. Review b08a0149media, b09c0149codes and b10d067discount first. ONLY after backup and target verification, run:

    python -m alembic upgrade head
    python -m alembic current
    python scripts/check_stage_schema_v066.py

Expect campaign_media, customer_codes, discount_reconciliation to PASS. Do not run Alembic downgrade; b08-b10 intentionally prohibit destructive reversal.

## Windows PowerShell clean-source verification

This checks out a separate detached worktree, preserving existing local staging files.

    $ErrorActionPreference = 'Stop'
    $repo = Join-Path $HOME 'Personal\Project\Pruvs-Stage-UX-20261110'
    $branch = 'release/pruvs-platform-v7151-b067-combined-stage-20261112'
    $verify = Join-Path $HOME 'Personal\Project\Pruvs-v7151-Verification'
    git -C $repo fetch origin $branch
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
    if (Test-Path $verify) { throw 'Verification directory exists; do not overwrite it' }
    $sha = (git -C $repo rev-parse "origin/$branch").Trim()
    git -C $repo worktree add --detach $verify $sha
    if ($LASTEXITCODE -ne 0) { throw 'Worktree failed' }
    Set-Location (Join-Path $verify 'backend')
    py -3.12 -m venv .stagevenv
    & .\.stagevenv\Scripts\python.exe -m pip install -r requirements.txt -r business-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Install failed' }
    & .\.stagevenv\Scripts\python.exe -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py tests/test_stage_v067.py
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
    Push-Location frontend
    npm ci; if ($LASTEXITCODE -ne 0) { throw 'Core install failed' }
    npm test; if ($LASTEXITCODE -ne 0) { throw 'Core tests failed' }
    npm run build; if ($LASTEXITCODE -ne 0) { throw 'Core build failed' }
    Pop-Location
    & .\.stagevenv\Scripts\python.exe scripts/check_react_build.py
    if ($LASTEXITCODE -ne 0) { throw 'Core build manifest failed' }
    Push-Location business_frontend
    $env:VITE_API_BASE='/business'
    $env:VITE_PRUVS_CUSTOMER_URL=''
    npm ci; if ($LASTEXITCODE -ne 0) { throw 'Business install failed' }
    npm run build -- --base=/business/
    if ($LASTEXITCODE -ne 0) { throw 'Business build failed' }
    Pop-Location
    Remove-Item Env:VITE_API_BASE,Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
    git -C $verify status --short

Do not run git add . or commit generated local bundles, venv, backups or node_modules. Branch source is already in GitHub. For future source edits, selectively stage only explicit changed paths (git add -- path1 path2), inspect git diff --cached --check and git diff --cached, then commit/push only the approved release branch. Never force-push or push this staging work into main.

## Render configuration AFTER the database gate

Use existing service Pruvs-staging with repository MelinteB/Pruvio. Change branch only to release/pruvs-platform-v7151-b067-combined-stage-20261112, root directory backend, auto-deploy OFF. Preserve the existing combined Python Build and Start commands. The existing Bash Start command must continue using app.platform_combined:app and PORT.

Recommended Build Command (Bash; root backend):

    pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py tests/test_combined_database_url_v066.py tests/test_stage_v067.py

Use these existing or required staging settings:
- DATABASE_URL: Core staging only; BUSINESS_DATABASE_URL: Business staging only.
- PRUVS_PLATFORM_COMBINED_STAGING=true; CANONICAL_REDIRECT_ENABLED=false.
- BUSINESS_JWT_SECRET and PRUVS_BRIDGE_SECRET are distinct, valid secrets already used by the staging apps.
- PRUVS_LOYALTY_ENABLED=true.
- Do NOT enable new features for all customers by default.

After changing Render Settings, manually deploy the latest commit. Verify deployed commit SHA against the release branch.

## Receipt pilot (enable only for validated pilot users and merchants)

    PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED=true
    PRUVS_LOYALTY_RECEIPT_V06_ENABLED=true
    PRUVS_LOYALTY_CUSTOMER_CODES_V12_ENABLED=true
    PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS=<comma-separated pilot Core user IDs>
    PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED=true
    PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED=true
    PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS=<comma-separated pilot Business merchant UUIDs>
    PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE=true

Only activate after database readiness and merchant receipt-review permissions are confirmed. The Business Purchase codes legacy panel may remain disabled while the customer-code pilot runs via Receipt claims.

## Optional campaign AI and artwork storage

    PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED=true
    OPENAI_API_KEY=<backend-only secret>
    PRUVS_CAMPAIGN_AI_MODEL=gpt-6-luna
    PRUVS_CAMPAIGN_R2_ENDPOINT_URL=<approved HTTPS endpoint>
    PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID=<backend-only key>
    PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY=<backend-only secret>
    PRUVS_CAMPAIGN_R2_BUCKET=<dedicated campaign bucket>
    PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL=<HTTPS public campaign CDN prefix>
    PRUVS_CAMPAIGN_MEDIA_HOSTS=<comma-separated allowlisted CDN domains>

The media generator builds a watermarked, branded 4:5 creative from the merchant's own photo. GIF and MP4 are approximately three seconds, with simple animation—not AI-generated video scenes. AI generates reviewable copy/creative directions and cannot modify program financial terms or publish campaigns. Publishing is explicitly controlled by merchant staff.

## Smoke test and manual acceptance

Once Render reports Live, run the read-only PowerShell verification script included in this branch:

    $script = Join-Path $HOME 'Personal\Project\Pruvs-v7151-Verification\scripts\Verify-Pruvs-Combined-Staging-v7151-b067.ps1'
    & $script

Expected Core health version 7.1.51 and Business health version 0.6.7; Business ready 200. If ready returns 503, STOP and inspect migration status before enabling loyalty.

Manual acceptance:
1. Archive/remove Core receipts and splits; they disappear from Project candidates and server rejects re-adding them.
2. Test right swipe increases quantity, left swipe reduces, long hold half/all, double-tap half/zero. Repeat on iOS Safari and Android Chrome; plus/minus must still work.
3. Verify green Business favicon at /business and blue Core favicon at /.
4. Join a published loyalty program, upload completed receipt, choose program, consent and generate claim QR. Business Receipt claims finds code, requires image review, then approves or rejects; no stamps before approval.
5. Once sufficient approved receipts earn a reward, Core wallet reserves checkout QR. Merchant verifies in Checkout & integrations; applies POS discount outside Pruvs, enters completed fiscal sale reference/amount, confirms redemption once. Both apps show reconciliation. Replaying voucher must fail.
6. Merchant can edit/pause/resume program; published financial criteria locked. Consumer leave cannot discard stamps or pending rewards.
7. With optional credentials, generate AI copy grounded in program terms, upload image, render a branded GIF/MP4, review draft, manually publish, verify Core media and 4:5 mobile layout.

## Rollback

Do not delete the old Business staging service or source branches. If release acceptance fails, return Pruvs-staging to release/pruvs-platform-v7150-b066-combined-stage-20261112 with its previous working Render settings; redeploy that commit. Restore a database backup ONLY if a reviewed corrective procedure actually requires it; never automatically downgrade the additive b08/b09/b10 schema and never delete financial audit data. No production changes are authorized by this plan.
