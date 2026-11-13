# Read-only acceptance gate for combined Core 7.1.56 + Business 0.6.12.
# Use against the ISOLATED staging service only. No database or API writes.
[CmdletBinding()]
param(
  [string]$BaseUrl='https://pruvs-core-staging.onrender.com',
  [switch]$RequireDatabaseMode,
  [string]$ExpectedMerchantStatus=''
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$base=$BaseUrl.TrimEnd('/')
if ($base -notmatch '^https://[^/]+$' -or
    $base -eq 'https://pruvs.io' -or
    $base -eq 'https://www.pruvs.io') {
  throw 'STOP: HTTPS staging origin required. Do not test production.'
}
function Fetch($path,$headers=@{}) {
  Invoke-RestMethod -Uri "$base$path" -Headers $headers -TimeoutSec 40
}
$core=Fetch '/health'
$business=Fetch '/business/health'
if($core.version -ne '7.1.56' -or $business.version -ne '0.6.12') {
  throw "Version mismatch: Core $($core.version), Business $($business.version)."
}
Write-Host 'PASS: Core 7.1.56 and Business 0.6.12' -ForegroundColor Green
$offers=@(Fetch '/business/v1/discover')
foreach ($offer in $offers) {
  if ($null -eq $offer.merchant_id -or
      $null -eq $offer.receipt_pilot_allowed) {
    throw 'Business discovery missing authoritative merchant pilot eligibility fields.'
  }
}
Write-Host "PASS: discovery API with $($offers.Count) offer(s)" -ForegroundColor Green
$token=$env:PRUVS_BUSINESS_STAGING_TOKEN
if(-not $token){
  if($RequireDatabaseMode -or $ExpectedMerchantStatus) {
    throw 'Set PRUVS_BUSINESS_STAGING_TOKEN to a short-lived staging merchant session token.'
  }
  Write-Warning 'Merchant-specific pilot status skipped (no staging token).'
  return
}
$auth=@{Authorization="Bearer $token"}
$access=Fetch '/business/v1/merchant/pilot-access' $auth
$ready=Fetch '/business/v1/merchant/receipt-pilot/readiness' $auth
Write-Host "Pilot mode: $($access.mode); merchant status: $($access.status)"
Write-Host "Receipt readiness: $($ready.status); enrollment schema: $($ready.merchant_pilot_schema_ready)"
if($RequireDatabaseMode -and
   ($access.mode -ne 'database' -or -not $ready.merchant_pilot_schema_ready)) {
  throw 'Database enrollment was not enabled or b11 migration was not verified.'
}
if($ExpectedMerchantStatus -and $access.status -ne $ExpectedMerchantStatus) {
  throw "Expected $ExpectedMerchantStatus; got $($access.status)."
}
Write-Host 'PASS: read-only merchant enrollment diagnostics.' -ForegroundColor Green
