# Pruvs v6.12.0 — Web Push enrolment and notifications

Update for an existing **v6.11.1** installation. Install v6.11 and v6.11.1 first if they are not installed. This is an update package, not a replacement for the full application.

## Included

- Notification setup after registration/sign-in, with a Continue option.
- A notification bell in the app header and a `/notifications` settings page.
- iPhone/iPad Home Screen guidance, browser permission prompt triggered directly by a tap, and manual device-settings guidance when blocked.
- Server-sent test notification. Tapping it confirms receipt for that device and login. Permission granted and test confirmed are separate states.
- Multiple devices, disabling individual devices, category preferences, and recent notification history.
- Receipt processed/failed, bill settled/reopened, and owner-triggered payment reminders connected to a persistent database outbox.
- Up to three attempts for transient push failures; revoked subscriptions are disabled. Email fallback uses existing Resend/SMTP settings and requires a verified email.
- Logout/account-switch revocation on the server. All new notification API endpoints require an authenticated browser grant. Click-through pages recheck the logged-in user's access.
- Root-scoped service worker, preserving existing static caching. Lock-screen business notifications are generic; bill details appear after opening Pruvs.
- Guarded installer, compatibility check, backups, automatic rollback on installation failure, and repeat-install detection.

The app cannot reliably open the device's notification settings directly. The first Enable tap opens the native permission prompt; if blocked, the page explains where to change settings manually. It never claims permission was granted when it was not.

## 1. Extract the package (PowerShell)

Download `pruvs_v6_12_web_push.zip` to Downloads. Run:

```powershell
$zip = Join-Path $env:USERPROFILE 'Downloads\pruvs_v6_12_web_push.zip'
$updates = Join-Path $env:USERPROFILE 'Downloads\pruvs_v6_12_update'
Expand-Archive -LiteralPath $zip -DestinationPath $updates -Force
$package = Join-Path $updates 'pruvs_v6_12_web_push'
Set-Location 'C:\Users\bogdan.melinte\Personal\Project\Pruvs'

if (Test-Path '.\app\main.py') {
    $backend = (Get-Location).Path
} elseif (Test-Path '.\backend\app\main.py') {
    $backend = (Resolve-Path '.\backend').Path
} else {
    throw 'Backend not found. Open the Pruvs folder containing app/main.py or backend/app/main.py.'
}
$backend
git status --short
```

Save or commit unrelated local changes first. Use your existing Python virtual environment. If it is not activated, activate the `.pvenv` you normally use for this project. The installer also accepts the project root and automatically detects its backend subfolder, avoiding the previous `--backend .` directory error.

## 2. Check and install

```powershell
python "$package\install.py" --backend "$backend" --check
if ($LASTEXITCODE -ne 0) { throw 'Compatibility check failed. Nothing was changed.' }
python "$package\install.py" --backend "$backend"
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Stop here.' }
Set-Location $backend
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
python -m compileall -q app
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
```

If compatibility fails, do not copy the `backend` folder over your app manually. The installer reports the exact differing file; provide that current file for an adapted patch. The installer applies targeted edits and preserves unrelated code. Backups are under `backend/update_backups/` (or `update_backups/` when your repository is itself the backend).

Optional automated tests:

```powershell
python -m pip install pytest
python -m pytest tests/test_web_push_v6_12.py -q --disable-warnings
if ($LASTEXITCODE -ne 0) { throw 'Notification tests failed.' }
```

## 3. Generate VAPID keys locally

Generate ONE key pair and retain it across deployments. Replace the example email with an actual address you control.

```powershell
$secretFolder = Join-Path $env:USERPROFILE 'PruvsSecrets'
New-Item -ItemType Directory -Path $secretFolder -Force | Out-Null
python "$package\scripts\generate_vapid.py" --subject 'mailto:YOUR_REAL_EMAIL' --out "$secretFolder\pruvs-push.private.env"
if ($LASTEXITCODE -ne 0) { throw 'VAPID generation failed. Check the email or existing output file.' }
notepad "$secretFolder\pruvs-push.private.env"
```

The script refuses to overwrite an existing key file. The private key is generated on your computer, not shipped in the update. Do not put the private settings in Git. If keys are rotated later, users must disable and re-enable notifications to create subscriptions for the new public key.

## 4. Render environment

In your existing Pruvs Render web service, open **Environment**. Copy the generated values exactly:

| Name | Value |
|---|---|
| `PRUVS_PUSH_ENABLED` | `true` |
| `PRUVS_PUSH_WORKER_ENABLED` | `true` |
| `PRUVS_VAPID_PUBLIC_KEY` | Generated public key |
| `PRUVS_VAPID_PRIVATE_KEY` | Generated private key |
| `PRUVS_VAPID_SUBJECT` | Your `mailto:` contact address |
| `PUBLIC_BASE_URL` | `https://pruvs.io` |

Preserve `DATABASE_URL`, `PRUVIO_STORAGE_SECRET`, existing OCR configuration and email settings. Use your durable PostgreSQL database on Render. No manual SQL migration is needed: five additive notification tables are created during application startup. Existing bill/user tables are not changed by this update.

For Resend fallback, retain `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, and `EMAIL_FROM`. SMTP is also supported through your existing `SMTP_*` settings. Account → Product notifications is the existing master preference for business notifications; the new page adds category/channel choices. Test pushes remain possible when business notifications are muted.

**The server must remain running to process the queue while users are away.** Use an always-on Render service for reliable unattended delivery. Render's Free web services spin down after 15 minutes without inbound activity; queued retries will wait while the process is asleep. This package runs a small worker inside the web process, polling every five seconds. It does not require Redis, OneSignal or a second Render service.

Keep your existing build/start commands; make sure the build installs the backend `requirements.txt`. Deploy the new code after setting the environment values. Do not run extra worker replicas manually for this initial rollout. Queue claiming is database-guarded, but the baseline NiceGUI session storage also has its own multi-instance considerations.

## 5. Commit only the update files and deploy

From the PowerShell session above:

```powershell
Set-Location $backend
$files = @(
    'app/main.py',
    'app/ui/app_shell.py',
    'app/ui/auth_state.py',
    'app/ui/notifications_ui.py',
    'app/api/push_notifications.py',
    'app/models/push_notification.py',
    'app/services/push_service.py',
    'app/services/push_worker.py',
    'app/services/standalone_app_service.py',
    'app/services/split_bill_session_service.py',
    'app/static/service-worker.js',
    'app/static/pruvs-push.js',
    'requirements.txt',
    'tests/test_web_push_v6_12.py'
)
git add -- $files
if ($LASTEXITCODE -ne 0) { throw 'Git staging failed.' }
git diff --cached --stat
git diff --cached --name-only
```

Confirm the staged list contains only the intended update and no private environment files. Then:

```powershell
git commit -m "Add Web Push enrolment and device confirmation v6.12"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
git push
if ($LASTEXITCODE -ne 0) { throw 'Push failed.' }
```

Wait for Render's deployment, or use **Manual Deploy → Deploy latest commit** if automatic deployment is off.

```powershell
Invoke-RestMethod 'https://pruvs.io/health' | Format-List
```

The health version should be `6.12.0`. Refresh Pruvs to load the new service worker. Existing logged-in users can tap the bell without logging out.

## 6. Acceptance test on real devices

1. On iPhone/iPad (16.4+): open pruvs.io in Safari → Share → Add to Home Screen. Open the icon and sign in. On Android/desktop use a supported browser.
2. In notification setup, tap **Enable notifications on this device**, then **Allow**. A real push test is queued automatically.
3. Leave Pruvs or lock the phone. Tap the arriving Pruvs notification. The page must show **Test notification confirmed on this device**.
4. Trigger an owner payment reminder while the participant's Pruvs is closed. Confirm a system notification arrives and opens the participant's bill after login/access checks.
5. Test receipt completion, bill settlement and reopening. Test on a second device under the same user.
6. Sign out on one device. Its server subscription must be disabled; the second device remains active. Sign in as a different user and enrol separately.
7. Block permission, reload, and verify the settings instructions appear. Denied permission cannot be overridden by Pruvs.
8. Disable push and leave email fallback enabled. Trigger a new reminder and check the verified email and notification history.

A device permission grant alone is never labelled as receipt confirmed. Confirmation expires after 15 minutes if the test has not been tapped; resend after at least 30 seconds. Normal notifications are sent only to devices with a confirmed test. Browser grants expire after 30 days; revisiting settings can renew the grant and requires confirming a new test. Signing out also requires a new confirmation next time.

## Delivery semantics and scope

- `accepted` means a push provider accepted the message, not that the user saw it. Focus, OS permissions, offline devices and force-stopped browsers may delay/suppress display. `email_accepted` likewise means accepted by the email provider.
- Email fallback occurs when no confirmed eligible device exists, or every attempted device fails after retries. It is not sent merely because an accepted push was not tapped; Web Push does not supply a dependable display receipt.
- Pushes use a 15-minute provider TTL. Business queue events expire after one day; scheduled events use a one-day window after their requested send time. Pending work survives restarts in the database. SMTP and crash-window retries can produce duplicates; notifications use a stable tag to reduce duplicate banners.
- A push already accepted by the provider cannot be recalled at logout. Generic business text avoids exposing receipt details; opening it still requires the right account.
- Existing invitation sharing remains unchanged. There is no new push invitation to an unknown/unregistered recipient. This update connects the existing receipt, bill-state, and participant-reminder actions; it does not add a contact directory or an automatic reminder scheduling screen.
- The queue API supports a future `when` in server code for later scheduling work. The UI currently sends reminders when the owner requests them.
- New endpoint validation permits the standard Apple, Google, Mozilla and Windows push services; an unsupported browser service returns a clear error rather than accepting an arbitrary outbound URL.
- This adds notification access controls; it is not a general security rewrite of pre-existing legacy application APIs.

## Rollback

Set `PRUVS_PUSH_WORKER_ENABLED=false` and `PRUVS_PUSH_ENABLED=false`. Revert the dedicated v6.12 Git commit and redeploy, or restore the installer backup locally before deploying. Keep the additive tables during rollback; deleting them is unnecessary. Disable device notifications from the browser/OS if you also want to remove its subscription. The old app does not use the new tables.

## Validation and sources

Automated checks cover subscription ownership, invalid endpoints, authentication/revocation, confirmation expiry, queue retry/recovery, multiple devices, preference enforcement and email fallback. Real APNs/FCM delivery must be tested after deployment with your own VAPID keys and devices; it cannot be proved by local mocks.

- Apple Web Push requirements: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- Browser permission API: https://developer.mozilla.org/en-US/docs/Web/API/Notification/requestPermission_static
- Python Web Push library: https://github.com/web-push-libs/pywebpush
- Render always-on considerations: https://render.com/docs/free
