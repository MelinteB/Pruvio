# Read-only AI campaign smoke check for Pruvs Core 7.1.55 / Business 0.6.11.
# Use on an ISOLATED STAGING URL only. Never creates, edits or publishes data.
[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://pruvs-core-staging.onrender.com',
    [string]$PromotionId = '',
    [ValidateSet('unspecified','published','unpublished')]
    [string]$ExpectedState = 'unspecified',
    [switch]$RequireAIReady
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$base = $BaseUrl.TrimEnd('/')
if ($base -eq 'https://pruvs.io' -or $base -eq 'https://www.pruvs.io') {
    throw 'STOP: this read-only verification script is staging-only.'
}
$core=Invoke-RestMethod -Uri "$base/health" -TimeoutSec 35
$business=Invoke-RestMethod -Uri "$base/business/health" -TimeoutSec 35
if ($core.version -ne '7.1.55' -or $business.version -ne '0.6.11') {
    throw "Unexpected staging versions Core=$($core.version) Business=$($business.version)"
}
Write-Host 'PASS: Core 7.1.55 + Business 0.6.11' -ForegroundColor Green
$public=Invoke-RestMethod -Uri "$base/business/v1/promotions?limit=30" -TimeoutSec 35
$campaigns=@($public)
Write-Host "PASS: public promotions endpoint returned $($campaigns.Count) row(s)" -ForegroundColor Green
if ($PromotionId) {
    $visible=@($campaigns | Where-Object { $_.id -eq $PromotionId }).Count -gt 0
    if ($ExpectedState -eq 'published' -and -not $visible) { throw 'Expected published campaign was not publicly visible.' }
    if ($ExpectedState -eq 'unpublished' -and $visible) { throw 'Unpublished campaign is still publicly visible.' }
    Write-Host "Campaign visibility: $visible (expected: $ExpectedState)"
}
$token=$env:PRUVS_BUSINESS_STAGING_TOKEN
if ($token) {
    $headers=@{ Authorization = "Bearer $token" }
    try {
        $ready=Invoke-RestMethod -Uri "$base/business/v1/merchant/promotions/ai-readiness" -Headers $headers -TimeoutSec 35
    } catch {
        throw 'Could not read authenticated Business AI readiness. Check staging account access and token.'
    }
    Write-Host "AI copy configured: $($ready.copy_ready)"
    Write-Host "AI artwork configured: $($ready.artwork_ready)"
    Write-Host "Campaign schema ready: $($ready.campaign_schema_ready)"
    if ($RequireAIReady -and (-not $ready.copy_ready -or -not $ready.artwork_ready -or -not $ready.campaign_schema_ready)) {
        throw 'AI campaign is not ready for staging acceptance.'
    }
} elseif ($RequireAIReady) {
    throw 'Set PRUVS_BUSINESS_STAGING_TOKEN securely in this shell to check authenticated AI readiness.'
} else {
    Write-Warning 'AI readiness not checked: set PRUVS_BUSINESS_STAGING_TOKEN in this shell (never commit it).'
}
Write-Host 'Read-only campaign smoke checks completed; paid generation and merchant/customer journey need manual acceptance.' -ForegroundColor Cyan
