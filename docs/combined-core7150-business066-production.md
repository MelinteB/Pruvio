# Pruvs production combined service — Core v7.1.50 / Business v0.6.6

**Release candidate**: `release/pruvs-platform-v7150-b066-combined-prod-20261113` in `MelinteB/Pruvio`.

This promotes the existing combined staging architecture to production *without copying staging credentials or data*. It is a production **release candidate**, not an instruction to change the active production service before verification.

## Target topology

- Core UI `/`, Core APIs `/api/v1/*`, Core health/readiness `/health` / `/ready`.
- Business UI `/business/`, merchant enroll `/business/merchant-enroll.html`, Business API `/business/v1/*`.
- Business health/readiness `/business/health` and `/business/ready`.
- Independent Core and Business logical PostgreSQL databases, existing production users and secrets.
- Core-to-Business loyalty calls use a fixed local loopback route `http://127.0.0.1:$PORT/business`, not a public external service.

## Blockers to resolve BEFORE changing production

1. Confirm the active Core production service, its GitHub branch, live commit, existing build/start commands, and backups in Render. GitHub `main` currently points to `b480ff1` (Core release candidate contains 27 later staging commits), so review all code changes before promoting; do not auto-merge this branch.
2. Confirm the **actual production** Core and Business database names from both Render connection strings. Do not use staging database URLs, names, or credentials. Record their exact names in `PRUVS_PRODUCTION_CORE_DB_NAME` and `PRUVS_PRODUCTION_BUSINESS_DB_NAME`.
3. Verify both production DB backups can be restored, then run read-only Business `/ready` schema checks. Business b08/b09 (and any newer) additive schema migrations must be applied separately and verified against the verified production Business DB, not from startup; never copy staging data.
4. Preserve Core's existing production `DATABASE_URL` and other environment variables. Supply `BUSINESS_DATABASE_URL` pointing to the existing **production Business** database (its current merchant records must remain intact), `BUSINESS_JWT_SECRET` with the existing production Business secret, and `PRUVS_BRIDGE_SECRET` with the existing matching production bridge secret.
5. Set `APP_ENV=production`, `PRUVS_PLATFORM_COMBINED_PRODUCTION=true`, `PRUVS_PLATFORM_COMBINED_STAGING=false`, `ENABLE_DEMO_SANDBOX=false`, and `CORS_ORIGINS=https://pruvs.io` (plus any additional explicitly approved HTTPS origins). Use distinct strong production signing secrets.
6. Keep production loyalty feature flags at their previous safe values until the smoke test is complete; turn on claims/customer codes only after testing both services.
7. Keep the standalone Business service available through the cutover and do not delete its database, service, repo, or secrets until post-cutover verification is complete.

## Render service configuration, after review

- Existing **Core production** Render Web Service, repo `MelinteB/Pruvio`, deploy branch `main`.
- Root Directory `backend`; use Python runtime. Consider pausing auto-deploy while the production change is being staged and reviewed.
- Build command (Render Bash):

```bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_combined_platform_routes.py tests/test_combined_database_url_v066.py tests/test_combined_production_config.py
```

- Start command (Render Bash):

```bash
exec python -m uvicorn app.platform_production:app --host 0.0.0.0 --port ${PORT:-10000}
```

This start command rejects any missing opt-in or mismatched/unknown database names. The staging `app.platform_combined` module remains staging-only.

## Production smoke checks (read-only first)

```powershell
$base = 'https://pruvs.io'
$paths = @('/health','/ready','/api/v1/release','/business/','/business/health','/business/ready','/business/merchant-enroll.html')
foreach ($path in $paths) {
    $response = Invoke-WebRequest -Uri ($base+$path) -MaximumRedirection 0 -SkipHttpErrorCheck
    Write-Host "$path : $($response.StatusCode)"
    if ($response.StatusCode -ne 200) { throw "Smoke check failed: $path" }
}
```

Also open `/business/`, confirm Business UI asset requests under `/business/assets/`, sign in with an existing production merchant, verify records, save a draft program, and test Pruvs customer loyalty visibility with an authorized test account. Validate that stamp credits require merchant approval and that no claim is duplicated. Check Core OCR, sign-in, bills, PWA and WebSocket behavior.

## Rollback

Preserve the prior successful Core production commit/branch and exact Build/Start configuration. If the combined deployment fails, restore the prior Core Start/Build command, unset `PRUVS_PLATFORM_COMBINED_PRODUCTION`, and redeploy the previous Core revision. Restore the Core loyalty API URL to the original standalone production Business endpoint if it was changed. Continue operating the original standalone Business service. No automatic database downgrade or destructive migration is part of rollback. Test both apps and both DB connections after rollback.

## Copy/paste Windows PowerShell 7 pre-merge verification

This workflow verifies the exact remote promotion branch in an **isolated Git worktree**,
leaving your normal local Core repository and working tree untouched. It does not
change production, push any code, stage local backups or require any database secrets.
The `main` merge and Render configuration are explicitly separate actions.

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\bogdan.melinte\Personal\Project\Pruvs'
$verifyDir = 'C:\Users\bogdan.melinte\Personal\Project\Pruvs-Combined-Prod-Verify'
$release = 'release/pruvs-platform-v7150-b066-combined-prod-20261113'
if (-not (Test-Path $repo)) { throw 'Core repository not found' }
if (Test-Path $verifyDir) { throw 'Verification worktree already exists: inspect it before rerunning' }
Set-Location $repo
if (@(git status --porcelain).Count -gt 0) { throw 'Your normal Core working tree has changes; do not overwrite them' }
git fetch origin --prune
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
git worktree add --detach $verifyDir "origin/$release"
if ($LASTEXITCODE -ne 0) { throw 'Verification worktree creation failed' }
Set-Location $verifyDir
$sha = (git rev-parse HEAD).Trim()
Write-Host "Promotion commit $sha"
git log -1 --oneline
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
if ($LASTEXITCODE -ne 0) { throw 'Git diff failed' }
if (@(git status --porcelain).Count -gt 0) { throw 'New verification worktree is not clean' }

py -3.12 -m venv .verifyenv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment unavailable' }
$python = Join-Path $verifyDir '.verifyenv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& $python -m pip install 'fastapi>=0.116,<1' 'httpx>=0.27,<1' 'sqlalchemy>=2.0,<3' 'pydantic-settings>=2.5,<3' 'pytest>=8,<10'
if ($LASTEXITCODE -ne 0) { throw 'Test dependencies failed to install' }
Push-Location backend
& $python -m compileall -q app/platform_production.py app/platform_combined.py app/react_app/loyalty_gateway.py business
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed' }
& $python -m pytest -q tests/test_combined_platform_routes.py tests/test_combined_database_url_v066.py tests/test_combined_production_config.py tests/test_stage_schema_v066.py
if ($LASTEXITCODE -ne 0) { throw 'Python regression tests failed' }

Push-Location frontend
$env:VITE_PRUVS_CORE_V7140_ENABLED = 'true'
$env:VITE_PRUVS_CORE_V7141_PROJECTS_ENABLED = 'true'
$env:VITE_PRUVS_LOYALTY_UI_ENABLED = 'true'
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Core npm installation failed' }
npm test
if ($LASTEXITCODE -ne 0) { throw 'Core frontend tests failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Core frontend build failed' }
Pop-Location
& $python scripts/check_react_build.py
if ($LASTEXITCODE -ne 0) { throw 'Core release build verification failed' }

Push-Location business_frontend
$env:VITE_API_BASE = '/business'
$env:VITE_PRUVS_CUSTOMER_URL = ''
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Business npm installation failed' }
npm run build -- --base=/business/
if ($LASTEXITCODE -ne 0) { throw 'Business frontend build failed' }
if (-not ((Get-Content dist/index.html -Raw).Contains('/business/assets/'))) { throw 'Incorrect Business asset base path' }
Pop-Location
Pop-Location
Write-Host 'Verification completed; see GitHub PR #6 for review. No deployment has occurred.'
```

Do not `git add .` or commit generated `dist` files, `.verifyenv` files, backups, secrets, or unrelated local changes from this verification worktree. If a subsequent code fix is necessary, create a separate fix branch, use explicit path staging (`git add -- path1 path2`), run `git diff --cached --check`, inspect `git diff --cached` and `git status`, and push only that fix branch to the PR.

### Controlled main promotion and deployment

After the production DB snapshots and Render service configuration are verified, temporarily disable Core production auto-deploy. On the verified PR, approve and merge via the GitHub UI (or, **only after explicitly accepting the cutover**, run `gh pr ready 6; gh pr checks 6; gh pr merge 6 --squash`). This updates `main`, but with auto-deploy OFF it does not intentionally initiate the production cutover. In Render, retain the previous production revision and commands; set the production environment variables and the combined Build/Start commands shown above. Deploy the reviewed main revision manually and run the smoke tests. Keep the standalone Business production service available throughout. Do not remove or alter either database during release. If the health checks fail, restore the previously recorded Core revision, original Build/Start commands and external Business endpoint, then recheck Core and standalone Business separately.
