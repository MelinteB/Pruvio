# Core 7.1.72 / Business 0.6.25 — campaign media lifecycle

## Scope

This increment adds an ownership registry for newly uploaded campaign source
photos and rendered campaign artwork. Saving or editing a promotion associates
those media keys with the merchant-owned promotion. The cleanup command only
considers registered keys that have remained unlinked for at least 30 days.

The change is additive. Existing public campaign assets and saved campaign
records are preserved. The registry does not make objects private: the current
R2 public delivery path remains in use. Private draft buckets, legacy artwork
regeneration, multi-photo montage, and authenticated PWA/bilingual acceptance
remain outstanding release work.

## Business database migration

The user authorized applying b14, b15 and b16 to staging without a backup.
The staging Render start command runs
`backend/scripts/apply_staging_business_migrations.py` before starting the app.
The runner accepts only PostgreSQL database `pruvs_business_staging` with
`PRUVS_PLATFORM_COMBINED_STAGING=true`, applies the three reviewed SQL files in
order, and verifies their tables. If the Business role lacks DDL permission, it
can use the existing Core URL only when it points to the same Postgres host and
can create tables; it grants the least-privilege Business role CRUD access to
the resulting tables. It is idempotent and refuses a different database.
Production is not a target of this deployment. The migrations add tables and
indexes; they do not rewrite existing campaign or customer rows.
The `/ready` endpoint reports unavailable until the registry and required
schema are present.

## Orphan cleanup

Run from `backend` with the Business database and campaign R2 credentials loaded.
The first invocation is a dry run and prints eligible keys only:

```powershell
python .\scripts\cleanup_campaign_media_orphans.py --older-than-days 30 --limit 250
```

Review the listed keys and confirm the configured bucket name before deletion.
The explicit apply form is:

```powershell
python .\scripts\cleanup_campaign_media_orphans.py `
  --older-than-days 30 `
  --limit 250 `
  --apply `
  --confirm-bucket '<exact-staging-bucket-name>'
```

The command refuses retention periods under 30 days and non-PostgreSQL
databases. It locks and removes one unlinked registry row at a time; if object
deletion fails, it leaves the row for a later retry. Run the report first and
keep the initial production rollout disabled until authenticated staging
acceptance is documented.

## Release acceptance still needed

- Confirm b14, b15 and b16 were applied and verified in staging by startup logs.
- Confirm `/ready` reports all checks ready and upload/render/save/edit works
  for an owner and manager account.
- Confirm campaign source and render keys attach to their promotion and are
  excluded from cleanup after attachment.
- Run cleanup in dry-run mode on staging, verify the proposed keys are old and
  unlinked, then apply only after explicit operator review.
- Complete the authenticated receipt-to-reward journey and retain existing
  pending claims and earned rewards.
- Keep production unchanged pending full acceptance.

## Windows PowerShell deployment procedure

Use a clean worktree at base commit `ceb6de95c5819e21829e5a184914712afce1823f`.
The package installer verifies the ZIP hash and base commit, backs up overwritten
files under the Windows temp directory, and copies only paths from the package
manifest.

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\<you>\Personal\Project\Pruvio'
$package = 'C:\Users\<you>\Downloads\Pruvs_Core_v7_1_72_Business_v0_6_25.zip'
$installer = Join-Path (Split-Path $package) 'Install-Pruvs-7.1.72-0.6.25.ps1'
$expectedSha256 = '<use the SHA-256 supplied with this package>'

if ((git -C $repo rev-parse HEAD).Trim() -ne 'ceb6de95c5819e21829e5a184914712afce1823f') {
    throw 'Unexpected base commit; stop and update the worktree to the release base.'
}
if (@(git -C $repo status --porcelain).Count -gt 0) {
    throw 'Worktree must be clean before package installation.'
}

Unblock-File -LiteralPath $installer
& $installer -RepoPath $repo -PackagePath $package -ExpectedSha256 $expectedSha256
if (-not $?) { throw 'Package installation failed.' }

# Backend and React checks/builds. These commands run on your workstation.
Set-Location (Join-Path $repo 'backend')
python -m pytest tests
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }

Set-Location (Join-Path $repo 'backend\frontend')
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Core frontend dependency install failed.' }
npm test
if ($LASTEXITCODE -ne 0) { throw 'Core React tests failed.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Core React build failed.' }

Set-Location (Join-Path $repo 'backend\business_frontend')
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Business frontend dependency install failed.' }
$env:VITE_API_BASE = '/business'
$env:VITE_PRUVS_CUSTOMER_URL = ''
npm run build -- --base=/business/
if ($LASTEXITCODE -ne 0) { throw 'Business frontend build failed.' }
Remove-Item Env:VITE_API_BASE, Env:VITE_PRUVS_CUSTOMER_URL -ErrorAction SilentlyContinue

Set-Location (Join-Path $repo 'backend')
python scripts/check_react_build.py
if ($LASTEXITCODE -ne 0) { throw 'Core release build check failed.' }

# Stage only files named by the update manifest, then inspect before committing.
$manifest = Join-Path (Split-Path $package) 'PACKAGE_MANIFEST.txt'
$files = @(Get-Content -LiteralPath $manifest | Where-Object { $_ -and (Test-Path (Join-Path $repo $_)) })
git -C $repo add -- $files
if ($LASTEXITCODE -ne 0) { throw 'Selective staging failed.' }
git -C $repo add -A -- backend/frontend/dist
if ($LASTEXITCODE -ne 0) { throw 'Core compiled assets staging failed.' }
git -C $repo diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed.' }
git -C $repo diff --cached --stat
git -C $repo diff --cached   # Review all staged code, migration and generated assets.

# Keep this on a feature branch for CI and staging review; do not push to main.
git -C $repo commit -m 'Pruvs Core v7.1.72 / Business v0.6.25 media lifecycle'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
git -C $repo push -u origin feature/core-7.1.72-business-0.6.25-media-lifecycle
if ($LASTEXITCODE -ne 0) { throw 'Feature branch push failed.' }
```

For staging, the authorized no-backup migration runner verifies the exact target
database before applying additive SQL. Roll back application code by redeploying
the previous tested commit; leave additive migration tables and their data in
place. Do not promote production until all receipt-to-reward and media lifecycle
acceptance is recorded.
