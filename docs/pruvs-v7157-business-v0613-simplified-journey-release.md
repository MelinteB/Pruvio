# Pruvs Core 7.1.57 + Business 0.6.13 — Simplified Loyalty Journey

Status: **candidate only**. These commits are NOT production or staging deployments. Do not point Render at either branch until CI and local tests complete.

- Core/combined repo: MelinteB/Pruvio
- Branch: release/pruvs-platform-v7157-b0613-simplified-journey-20261116
- Standalone Business: MelinteB/Pruvs-Business
- Branch: release/pruvs-business-v0.6.13-simplified-journey-20261116
- Existing staging service: srv-dbkrcaui0phs73b3h7p0 (Pruvs-staging).
- Staging DB revision already upgraded and verified: b11a0612pilot.
- Both staging recovery instance and downloaded Render export should be retained until acceptance.

## What changes

1. Merchant: "Loyalty programs" includes a 3-step activation checklist (location, published program, one-time approval). Existing draft programs are linked rather than duplicated. Approval updates are refreshed on focus and every 30 seconds while visible.
2. Platform admin: merchant workspace is hidden; a dedicated approval screen and history remain backed by Business's platform_admin JWT and b11 audit APIs. Pending/active/all filters and refresh are available.
3. Merchant purchase verification: clear language, status-aware help to activation, one-time code entry and explicit confirm/reject. There is no simulated POS settlement.
4. Customer Core: Saved receipts now explains "Earn stamps" and a server-issued one-time verification QR/code; explicit receipt sharing consent stays mandatory.
5. Backend authorization is unchanged: only platform_admin may approve/revoke, owners/managers request, and Business advertises approved status to Core. No schema migration beyond b11, no cross-service identity synchronization. Existing claim code expiry/unlock and audit remain enforced.
6. Camera scanning, push notifications and payment processor integration are NOT included in this candidate; code entry remains the merchant's fallback. Camera scanning requires a separate browser permission/security release.

## Windows PowerShell — independent verification in detached worktrees

Open a fresh PowerShell terminal. Node.js 22 and Python 3.12 must already be available. Do not use deployment secrets or Render database URLs for the isolated tests.

~~~powershell
$ErrorActionPreference='Stop'
$root=Join-Path $HOME 'Personal\Project'
$core=Join-Path $root 'Pruvs'
$business=Join-Path $root 'Pruvs-Business'
$coreBranch='release/pruvs-platform-v7157-b0613-simplified-journey-20261116'
$bizBranch='release/pruvs-business-v0.6.13-simplified-journey-20261116'
$coreVerify=Join-Path $root 'Pruvs-Core-v7157-Verify'
$bizVerify=Join-Path $root 'Pruvs-Business-v0613-Verify'
$python=(Get-Command python -ErrorAction Stop).Source
$pythonVersion=(& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if($pythonVersion -ne '3.12'){ throw "Requires Python 3.12, found $pythonVersion" }
& node --version
if($LASTEXITCODE -ne 0){throw 'Node unavailable'}
foreach($t in @(
    @{Repo=$core;Verify=$coreVerify;Branch=$coreBranch;Remote='MelinteB/Pruvio'},
    @{Repo=$business;Verify=$bizVerify;Branch=$bizBranch;Remote='MelinteB/Pruvs-Business'}
)){
    if(-not (Test-Path (Join-Path $t.Repo '.git'))){throw "Missing clone $($t.Repo)"}
    $remote=(git -C $t.Repo remote get-url origin)
    if($remote -notmatch [regex]::Escape($t.Remote)){throw "Unexpected origin: $remote"}
    if(Test-Path $t.Verify){throw "Worktree already exists: $($t.Verify). Review manually."}
    git -C $t.Repo fetch origin $t.Branch
    if($LASTEXITCODE -ne 0){throw "Fetch failed: $($t.Branch)"}
    $sha=(git -C $t.Repo rev-parse FETCH_HEAD).Trim()
    git -C $t.Repo worktree add --detach $t.Verify $sha
    if($LASTEXITCODE -ne 0){throw "Worktree creation failed: $($t.Verify)"}
    Write-Host "$($t.Remote) checkout: $sha"
}
# Verify combined Core backend and both React builds.
Push-Location (Join-Path $coreVerify 'backend')
try{
    & $python -m venv .verifyvenv
    if($LASTEXITCODE -ne 0){throw 'Core venv creation failed'}
    $py=Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
    & $py -m pip install -r requirements.txt -r business-requirements.txt
    if($LASTEXITCODE -ne 0){throw 'Core dependency installation failed'}
    & $py -m compileall -q business business_migrations app
    if($LASTEXITCODE -ne 0){throw 'Core syntax checks failed'}
    & $py -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py tests/test_pilot_enrollment_v0612.py tests/test_pilot_readiness_v069.py tests/test_receipt_code_access_v0610.py tests/test_campaign_journey_v0611.py tests/test_wallet_legacy_v068.py
    if($LASTEXITCODE -ne 0){throw 'Core backend tests failed'}
    Push-Location frontend
    try {
        & npm.cmd ci
        if($LASTEXITCODE -ne 0){throw 'Core npm ci failed'}
        & npm.cmd test
        if($LASTEXITCODE -ne 0){throw 'Core React tests failed'}
        & npm.cmd run build
        if($LASTEXITCODE -ne 0){throw 'Core React build failed'}
    } finally {Pop-Location}
    & $py scripts/check_react_build.py
    if($LASTEXITCODE -ne 0){throw 'Core stamped build verification failed'}
    Push-Location business_frontend
    try {
        $env:VITE_API_BASE='/business'
        $env:VITE_PRUVS_CUSTOMER_URL=''
        & npm.cmd ci
        if($LASTEXITCODE -ne 0){throw 'Combined Business npm ci failed'}
        & npm.cmd run build -- --base=/business/
        if($LASTEXITCODE -ne 0){throw 'Combined Business build failed'}
    } finally {
        Pop-Location
        Remove-Item Env:VITE_API_BASE,Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue
    }
} finally {Pop-Location}
# Verify independent Business backend and UI.
Push-Location (Join-Path $bizVerify 'backend')
try {
    & $python -m venv .verifyvenv
    if($LASTEXITCODE -ne 0){throw 'Business venv creation failed'}
    $py=Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
    & $py -m pip install -r requirements.txt
    if($LASTEXITCODE -ne 0){throw 'Business dependency installation failed'}
    & $py -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_pilot_readiness_v069.py tests/test_receipt_code_access_v0610.py tests/test_campaign_journey_v0611.py tests/test_wallet_legacy_v068.py
    if($LASTEXITCODE -ne 0){throw 'Business backend tests failed'}
} finally {Pop-Location}
Push-Location (Join-Path $bizVerify 'frontend')
try {
    & npm.cmd ci
    if($LASTEXITCODE -ne 0){throw 'Standalone Business npm ci failed'}
    & npm.cmd run build
    if($LASTEXITCODE -ne 0){throw 'Standalone Business build failed'}
} finally {Pop-Location}
foreach($path in @($coreVerify,$bizVerify)){
    git -C $path diff --check
    if($LASTEXITCODE -ne 0){throw "Git diff check failed: $path"}
    git -C $path status --short
}
Write-Host 'CANDIDATE VERIFICATION COMPLETE' -ForegroundColor Green
~~~

No \`git add .\` is required: these release branches are already committed in GitHub. If local edits must be made, create an editable worktree on the release branch and stage only reviewed paths with \`git add -- path1 path2\`, followed by \`git diff --cached --check\`, \`git diff --cached --stat\`, \`git diff --cached\`, commit and push. Never stage .env files, secrets, backups, dist folders or virtual environments by accident.

## Deployment gate

1. Confirm latest **GitHub Actions** checks on both candidate branch HEADs have passed.
2. Keep the original b07 recovery instance and Render export for rollback. No new database migrations are required (b11 already exists).
3. In Render, change ONLY Pruvs-staging to the new combined Core candidate branch and deploy it. Never change production branches, domains or DB URLs; no force-push. Confirm \`PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=true\` only on staging.
4. Check \`GET /health\` reports Core 7.1.57 and \`GET /business/health\` reports Business 0.6.13. Ensure Core build manifest reports 7.1.57; confirm \`/business/\` and public assets load. Confirm database remains b11.
5. Sign in as merchant: Loyalty programs checklist, existing draft/published program, Request activation. Sign in as dedicated platform admin: only approval workspace, Pending filter, Approve and audit. Return to merchant: Active status; Verify purchases now usable.
6. Core: Discover/Join a merchant program, Saved receipts -> Earn a stamp -> consent -> one-time QR/code. Business: enter the code, view consented receipt, verify sale, Confirm and add stamp; Core wallet updates. Test rejection, repeat verification prevention and admin revoke. Verify non-admin cannot approve and a newly registered merchant is never pre-approved.
7. When checks pass, manually consider a production release separately. No automatic promotion.

## Rollback

If new UI or behavior fails, revert only the staging Render branch to the previous verified Core 7.1.56 + Business 0.6.12 combined release (staging deploy d433c1fa05b73ceefe58f3c5a9850f5d670f574c). Do not run Alembic downgrade; b11 is additive and remains installed. If enrollment must be paused, set the staging-only \`PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=false\` (note this falls back to the pre-existing explicit static allowlist). Re-check merchant access and then decide rollback or targeted fix; do not expose production or recovery DB.

Platform credentials, database backups, API tokens and JWT secrets must never be committed or pasted into issue trackers/chat.
