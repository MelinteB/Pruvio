# Pruvs Core 7.1.59 — Scan to loyalty (STAGING demo)

Production is unchanged. Business API stays at 0.6.14 and its audited b11 database schema remains unchanged. Keep the Render export and recovery instance.

## Customer journey

1. Customer signs in, discovers and joins the published merchant program.
2. Merchant is approved by a separately provisioned Pruvs platform administrator.
3. Customer scans, crops and processes a complete receipt.
4. The receipt detail page immediately shows a new Earn a stamp panel; there is no detour to Saved receipts.
5. On the pruvs-core-staging.onrender.com demo host only, a merchant-name match suggests an approved joined program. The program title, store or registered merchant name may contain the normalized merchant text from the scanned receipt.
6. Click Earn a stamp, select the program, review and check readable, small, accessible consent.
7. The original JPG/PNG/WebP stored by Scan in per-user IndexedDB is reused automatically. If there is no device copy but the subscription has an original on the secure Core server, the server reads that stored image. No second upload dialog. Unsupported local PDFs, absent originals and scans exceeding the 6 MB secure evidence limit fail clearly.
8. A time-limited one-time QR/code is generated for the merchant. The merchant inspects the consented receipt preview and explicitly confirms the sale. Only Business confirmation credits stamps.
9. Test rejection, expired code, duplicated receipt, revoked merchant, missing receipt image and an unjoined customer; none may credit a stamp.

Name matching is a staging UI suggestion, not evidence of a real merchant payment. It cannot grant merchant pilot approval or issue credits by itself.

## PRODUCTION merchant QR — separate future backend release

For production do NOT trust OCR merchant-name similarity, a raw QR ID, or an unauthenticated customer-supplied merchant ID. The future POS/merchant receipt QR must include a versioned, issuer-verified merchant/store ID and a nonce or sale reference with signature. Server-side verification must validate issuer, merchant/store owner, signature, expiry and replay resistance, then reconcile amount/currency and merchant or POS confirmation. Business remains the authority for approved programs, and receipt image consent remains mandatory. This signed QR and POS validation are NOT implemented here.

## Isolated PowerShell verification

Requires an existing Pruvs repository at Personal\Project\Pruvs, Python 3.12 and Node.js 22. Never load staging/production DB credentials. Never overwrite an existing verification worktree.

~~~powershell
$ErrorActionPreference='Stop'
$root=Join-Path $HOME 'Personal\Project'
$repo=Join-Path $root 'Pruvs'
$verify=Join-Path $root 'Pruvs-v7159-Verify'
$branch='release/pruvs-core-v7159-scan-to-loyalty-demo-20261117'
if(Test-Path $verify){throw "Worktree already exists: $verify"}
if(-not (Test-Path (Join-Path $repo '.git'))){throw 'Pruvs clone missing'}
if((git -C $repo remote get-url origin) -notmatch 'MelinteB/Pruvio'){throw 'Unexpected repository origin'}
git -C $repo fetch origin $branch
if($LASTEXITCODE -ne 0){throw 'Fetch failed'}
$sha=(git -C $repo rev-parse FETCH_HEAD).Trim()
git -C $repo worktree add --detach $verify $sha
if($LASTEXITCODE -ne 0){throw 'Checkout failed'}
$python=(Get-Command python -ErrorAction Stop).Source
$ver=(& $python -c 'import sys;print(str(sys.version_info.major)+"."+str(sys.version_info.minor))').Trim()
if($ver -ne '3.12'){throw "Need Python 3.12; found $ver"}
Push-Location (Join-Path $verify 'backend')
try {
  & $python -m venv .verifyvenv
  if($LASTEXITCODE -ne 0){throw 'Python env failed'}
  $py=Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
  & $py -m pip install -r business-requirements.txt 'Pillow>=10,<13' 'python-multipart>=0.0.9'
  if($LASTEXITCODE -ne 0){throw 'Dependency installation failed'}
  & $py -m compileall -q app/react_app business business_migrations
  if($LASTEXITCODE -ne 0){throw 'Backend compile failed'}
  & $py -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_dynamic_customer_pilot_v7158.py tests/test_receipt_code_access_v0610.py
  if($LASTEXITCODE -ne 0){throw 'Business regressions failed'}
  Push-Location frontend
  try {
    $env:VITE_PRUVS_LOYALTY_UI_ENABLED='true'
    & npm.cmd ci
    if($LASTEXITCODE -ne 0){throw 'npm ci failed'}
    & npm.cmd test
    if($LASTEXITCODE -ne 0){throw 'React tests failed'}
    & npm.cmd run build
    if($LASTEXITCODE -ne 0){throw 'React build failed'}
  } finally {
    Pop-Location
    Remove-Item Env:VITE_PRUVS_LOYALTY_UI_ENABLED -ErrorAction SilentlyContinue
  }
  & $py scripts/check_react_build.py
  if($LASTEXITCODE -ne 0){throw 'Core build verification failed'}
  Push-Location business_frontend
  try {
    $env:VITE_API_BASE='/business'
    & npm.cmd ci
    if($LASTEXITCODE -ne 0){throw 'Business npm install failed'}
    & npm.cmd run build -- --base=/business/
    if($LASTEXITCODE -ne 0){throw 'Business build failed'}
  } finally {
    Pop-Location
    Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue
  }
} finally {Pop-Location}
git -C $verify diff --check
if($LASTEXITCODE -ne 0){throw 'Git diff check failed'}
git -C $verify status --short
Write-Host "PASS: Core v7.1.59 verified at $sha" -ForegroundColor Green
~~~

The implementation is already committed on its release branch. Do not use git add . or stage backups. For local changes, use git add -- path/to/reviewed-file, git diff --cached --check, git diff --cached --stat, git diff --cached, commit and push only the release branch.

## Staging deployment and rollback gate

Confirm latest GitHub Actions success before deploying the combined release on Pruvs-staging, not production. Verify the Core health endpoint reports 7.1.59, Business health reports 0.6.14, build manifest reports 7.1.59, and Business remains at b11. Staging feature flags for loyalty/customer codes must already be enabled. This version adds no DB migration and needs no new Render setting.

Rollback to the previous staging version Core 7.1.58 / Business 0.6.14 and the last verified staging commit if UI or consent verification fails. Keep b11 (no Alembic downgrade) and preserve the recovery export. Do not modify the production branch, service, domain or credentials.
