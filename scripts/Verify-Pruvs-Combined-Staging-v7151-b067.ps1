# Read-only combined Pruvs staging smoke checks. Never changes a database or account.
[CmdletBinding()]
param([string]$BaseUrl='https://pruvs-core-staging.onrender.com')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$base=$BaseUrl.TrimEnd('/')
function Check([string]$Path) {
    try {
        $r=Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 35
        if ($r.StatusCode -ne 200) {throw "HTTP $($r.StatusCode)"}
        Write-Host "PASS $($r.StatusCode) $Path" -ForegroundColor Green
        return $r
    } catch {
        throw "FAILED $Path — $($_.Exception.Message)"
    }
}
$core=(Check '/health').Content | ConvertFrom-Json
if ($core.version -ne '7.1.51') {throw "Core mismatch: $($core.version)"}
$business=(Check '/business/health').Content | ConvertFrom-Json
if ($business.version -ne '0.6.7') {throw "Business mismatch: $($business.version)"}
$ready=(Check '/business/ready').Content | ConvertFrom-Json
if ($ready.status -ne 'ready') {throw 'Business staging schema is not ready'}
Check '/api/v1/release' | Out-Null
Check '/' | Out-Null
Check '/business/' | Out-Null
Check '/business/business-favicon.svg' | Out-Null
Check '/business/merchant-enroll.html' | Out-Null
Check '/business/v1/discover' | Out-Null
Check '/business/v1/promotions?limit=5' | Out-Null
Write-Host 'PASS: Stage health, database readiness, release versions and public business routes' -ForegroundColor Cyan
Write-Host 'MANUAL ACCEPTANCE: receipt claim code QR, merchant image review, approval, voucher QR, completed sale reference and reconciliation.' -ForegroundColor Yellow
