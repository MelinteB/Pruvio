# Core v7.1.58 + Business v0.6.14 — Dynamic customer eligibility

**Candidate release. Production remains unchanged.**

- Combined Core/Business repository: \`MelinteB/Pruvio\`
- Release branch: \`release/pruvs-core-v7158-business-v0614-dynamic-customer-pilot-20261117\`
- Standalone Business: \`MelinteB/Pruvs-Business\`
- Release branch: \`release/pruvs-business-v0.6.14-dynamic-customer-pilot-20261117\`
- Staging Render service: \`Pruvs-staging\`; do not modify production.
- Business database migration: **no new migration**; b11 is the prerequisite.
- Recovery: retain pre-b11 recovery instance and original Render export until acceptance completes.

## Reason

Core previously checked \`PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS\` for numerical customer IDs (which differ across production/staging and new accounts). This release **does not read or require** a customer-ID list or customer-eligibility mode flag.

A signed-in Core account uses its authenticated server identity. Core produces a short-lived, signed pseudonymous customer token. The Business backend then checks in its database that:
1. The customer is a member of a **published** loyalty program.
2. The program belongs to an **active store**.
3. The merchant has the status **approved** in the existing b11 pilot enrollment.
4. The global receipt pilot remains enabled.

No public API accepts an arbitrary numeric customer ID. No customer identity is stored in Render settings for this purpose. If Business is unavailable or responds incorrectly, issuing a new receipt claim fails closed. A merchant may be revoked by a platform administrator; access is removed immediately. Already submitted claims remain readable.

Existing receipt-security safeguards remain: explicit sharing consent, saved-receipt ownership, limited image preview, signed amount/store/currency proof, replay prevention, merchant receipt review, code unlock and audited reward credit.

## Rollout order

1. Confirm both release candidates' latest GitHub Actions checks pass. Build failures block rollout.
2. Keep the existing recovery database and export. No Alembic migration is required.
3. Deploy the **combined Core + Business candidate together** to **Pruvs-staging**. Deploying Core alone makes dynamic eligibility fail closed until Business v0.6.14 is live.
4. Staging flags already used for the pilot still control global rollout:
   - \`PRUVS_LOYALTY_ENABLED=true\`
   - \`PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED=true\`
   - \`PRUVS_LOYALTY_RECEIPT_V06_ENABLED=true\`
   - \`PRUVS_LOYALTY_CUSTOMER_CODES_V12_ENABLED=true\`
   - \`PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED=true\`
   - \`PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED=true\`
   - \`PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE=true\`
   - \`PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED=true\`
5. **Do not populate or maintain** \`PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS\`. The new code ignores it. Existing values can be cleared after verification; do not remove deployment secrets.
6. As the merchant, publish a loyalty program with an active location and request approval under **Loyalty programs**.
7. As the separately provisioned platform administrator, approve the merchant.
8. As *any* signed-in Core customer (regardless of numeric ID), open **Discover**, join the approved merchant's program, then **Saved receipts**. The selected receipt shows **Earn a stamp**.
9. Consent to share the receipt, generate a one-time QR/code and have the merchant verify the purchase in **Verify purchases**.
10. Confirm one stamp is credited. Test with an unjoined customer, revoked merchant, expired code, wrong merchant, and repeated receipt: all must fail closed.

### Optional browser status check

Sign in to staging Core, open F12 Console, paste:

\`\`\`js
fetch('/api/v1/loyalty/status', {credentials:'same-origin',cache:'no-store'})
  .then(r=>r.json()).then(({enabled,receipt_claims_enabled,
    receipt_v06_enabled,customer_codes_v12_enabled,
    receipt_access_reason})=>console.table({
      enabled,receipt_claims_enabled,receipt_v06_enabled,
      customer_codes_v12_enabled,receipt_access_reason
    }));
\`\`\`

Expected **before** joining an approved program: \`receipt_v06_enabled=false\` and \`receipt_access_reason=no_joined_approved_merchant\`. Expected **after** joining: both verification booleans become \`true\` and reason \`joined_approved_merchant\`. No manual customer ID changes.

## Windows PowerShell: isolated candidate verification

Use Python 3.12 and Node.js 22. This worktree is independent from \`main\` and staging databases. **Do not load any Render credentials.**

\`\`\`powershell
$ErrorActionPreference='Stop'
$root=Join-Path $HOME 'Personal\Project'
$repo=Join-Path $root 'Pruvs'
$verify=Join-Path $root 'Pruvs-v7158-Verify'
$branch='release/pruvs-core-v7158-business-v0614-dynamic-customer-pilot-20261117'
if(Test-Path $verify){throw "Existing verification worktree: $verify. Inspect first."}
git -C $repo fetch origin $branch
if($LASTEXITCODE -ne 0){throw 'Fetch failed'}
$sha=(git -C $repo rev-parse FETCH_HEAD).Trim()
git -C $repo worktree add --detach $verify $sha
if($LASTEXITCODE -ne 0){throw 'Worktree checkout failed'}
$py=(Get-Command python -ErrorAction Stop).Source
Push-Location (Join-Path $verify 'backend')
try{
  & $py -m venv .verifyvenv
  if($LASTEXITCODE -ne 0){throw 'Python venv failed'}
  $isolated=Join-Path (Get-Location) '.verifyvenv\Scripts\python.exe'
  & $isolated -m pip install -r business-requirements.txt 'Pillow>=10,<13' 'python-multipart>=0.0.9'
  if($LASTEXITCODE -ne 0){throw 'Dependency install failed'}
  & $isolated -m pytest -q tests/test_pilot_enrollment_v0612.py tests/test_dynamic_customer_pilot_v7158.py tests/test_receipt_code_access_v0610.py
  if($LASTEXITCODE -ne 0){throw 'Backend validation failed'}
  Push-Location frontend
  try{
    & npm.cmd ci
    if($LASTEXITCODE -ne 0){throw 'Core npm install failed'}
    & npm.cmd test
    if($LASTEXITCODE -ne 0){throw 'Core React tests failed'}
    & npm.cmd run build
    if($LASTEXITCODE -ne 0){throw 'Core React build failed'}
  }finally{Pop-Location}
  & $isolated scripts/check_react_build.py
  if($LASTEXITCODE -ne 0){throw 'Core stamped build invalid'}
  Push-Location business_frontend
  try{
    $env:VITE_API_BASE='/business'
    & npm.cmd ci
    if($LASTEXITCODE -ne 0){throw 'Business npm ci failed'}
    & npm.cmd run build -- --base=/business/
    if($LASTEXITCODE -ne 0){throw 'Business React build failed'}
  }finally{Pop-Location;Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue}
}finally{Pop-Location}
git -C $verify diff --check
if($LASTEXITCODE -ne 0){throw 'Git diff check failed'}
Write-Host "CANDIDATE VERIFIED at $sha" -ForegroundColor Green
\`\`\`

The separate Business release should also pass its branch CI; local testing can use a second detached worktree with \`python -m pytest -q tests/test_pilot_enrollment_v0612.py\` and \`npm.cmd ci; npm.cmd run build\`.

### Git staging and deployment safety

All implementation files are already committed to release branches. Do not use \`git add .\`. For new local fixes, explicitly stage reviewed files: \`git add -- path/to/file\`, then \`git diff --cached --check\`, \`git diff --cached --stat\`, \`git diff --cached\`, commit, and push the *release branch*.

Check CI and production isolation before changing the Render staging branch. Verify \`GET /health\` returns Core 7.1.58 and \`GET /business/health\` returns Business 0.6.14, and inspect the Core build manifest. Production branch, production credentials, and production database must remain untouched.

Rollback: restore Pruvs-staging's prior combined release branch and commit (7.1.57 / 0.6.13 at \`86e12c8d87703c6f0c7ca6c3499fb37ff66a68db\`). The b11 database schema remains; no Alembic downgrade. If necessary disable only global receipt pilot flags on staging as an emergency stop. Do not roll back via production infrastructure.
