# Read-only combined staging smoke check — Core 7.1.52 + Business 0.6.8
# Run after Render reports Live. Does not change user data or any database.
[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://pruvs-core-staging.onrender.com',
    [switch]$RequireSchemaReady
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$base=$BaseUrl.TrimEnd('/')
function Check([string]$path) {
    try {
        $result=Invoke-WebRequest -Uri "$base$path" -UseBasicParsing -TimeoutSec 35
        if ($result.StatusCode -ne 200) { throw "HTTP $($result.StatusCode)" }
        Write-Host "PASS: $path" -ForegroundColor Green
        return $result
    } catch {
        throw "FAIL: $path - $($_.Exception.Message)"
    }
}
$core=(Check '/health').Content | ConvertFrom-Json
if ($core.version -ne '7.1.52') { throw "Core version mismatch: $($core.version)" }
$business=(Check '/business/health').Content | ConvertFrom-Json
if ($business.version -ne '0.6.8') { throw "Business version mismatch: $($business.version)" }
Check '/api/v1/release' | Out-Null
Check '/' | Out-Null
Check '/business/' | Out-Null
Check '/business/business-favicon.svg' | Out-Null
Check '/business/merchant-enroll.html' | Out-Null
Check '/business/v1/discover' | Out-Null

$schemaReady=$false
try {
    $ready=(Check '/business/ready').Content | ConvertFrom-Json
    $schemaReady=$ready.status -eq 'ready'
} catch {
    Write-Warning 'Business reconciliation/campaign schema is not ready. Complete verified staging-only migrations before activating receipt rewards or campaigns.'
}
if (-not $schemaReady -and $RequireSchemaReady) { throw 'Business staging database migration is required.' }
if ($schemaReady) {
    Check '/business/v1/promotions?limit=5' | Out-Null
} else {
    Write-Warning 'Campaign checks skipped while the database migration is pending.'
}
Write-Host 'Core and Business HTTP smoke checks completed.' -ForegroundColor Cyan
Write-Host 'Next: authenticated Wallet/memberships, merchant approval and checkout reconciliation must be tested manually.' -ForegroundColor Yellow
