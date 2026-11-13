# Read-only smoke verification for Pruvs Core + Business combined STAGING.
# Do not use this script as a database migration or deployment tool.
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'

    $base = 'https://pruvs-core-staging.onrender.com'
    $core = Invoke-RestMethod "$base/health"
    if ($core.status -ne 'ok' -or $core.version -ne '7.1.50') {
        throw "Core staging is not on v7.1.50. Got version: $($core.version)"
    }
    Write-Host 'PASS: Core health v7.1.50' -ForegroundColor Green

    $release = Invoke-WebRequest "$base/api/v1/release" -UseBasicParsing
    if ($release.StatusCode -ne 200) {
        throw 'Core release/build fingerprint does not match'
    }
    Write-Host 'PASS: Core React build fingerprint' -ForegroundColor Green

    $business = Invoke-RestMethod "$base/business/health"
    if ($business.status -ne 'ok' -or $business.version -ne '0.6.6') {
        throw "Business staging is not on v0.6.6. Got version: $($business.version)"
    }
    Write-Host 'PASS: Business health v0.6.6' -ForegroundColor Green

    try {
        $ready = Invoke-RestMethod "$base/business/ready"
        if ($ready.status -ne 'ready') { throw 'Schema unavailable' }
    }
    catch {
        throw 'Business schema NOT READY: verify backed-up staging Alembic revisions b08 and b09 before proceeding.'
    }
    Write-Host 'PASS: Business campaign media + receipt code schema' -ForegroundColor Green

    foreach ($path in @('/','/business/','/business/merchant-enroll.html','/business/merchant-login-entry.js','/business/merchant-login-entry.css')) {
        $response = Invoke-WebRequest ($base+$path) -UseBasicParsing
        if ($response.StatusCode -ne 200) { throw "Missing route: $path" }
        Write-Host "PASS: $path" -ForegroundColor Green
    }

    $offers = Invoke-WebRequest "$base/business/v1/discover" -UseBasicParsing
    $promos = Invoke-WebRequest "$base/business/v1/promotions?limit=3" -UseBasicParsing
    if ($offers.StatusCode -ne 200 -or $promos.StatusCode -ne 200) {
        throw 'Business loyalty discovery/campaigns are not healthy'
    }
    Write-Host 'PASS: Business loyalty discovery and campaigns' -ForegroundColor Green

    Write-Host ''
    Write-Host 'Read-only smoke tests passed. Continue with MANUAL merchant login, receipt claim, approval, notifications, mobile and data-isolation acceptance.' -ForegroundColor Cyan
}
