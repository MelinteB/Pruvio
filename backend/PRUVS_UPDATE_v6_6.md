# Pruvs v6.6 — live split selection and browser-session protection

Version endpoint after deployment: `/health` → `6.6.0`.

## What changed

- Split selections are saved immediately. There is no longer a **Save my selection** step.
- Open split pages poll for changes every ~0.6 seconds, so selections made by another participant are reflected automatically.
- Every receipt line shows who selected it and the selected quantity, including the current user, for example `✓ Ana Popescu ×1` and `✓ Bogdan Melinte · you ×2`.
- When the complete available quantity of a line has been selected by other participants, that line is greyed and struck through for the current participant.
- Assignment labels remain visible after settlement and after the owner reopens the bill. Reopening still preserves allocations and resets payment state.
- Selection writes are serialized per split session on databases that support row locking (including PostgreSQL), reducing races when two participants try to take the last available unit at nearly the same time.
- A live split page verifies the browser's trusted-device account every second. If another Pruvs account becomes active in that same browser profile, the previous split page is blocked so two different users cannot keep using the same browser session simultaneously.

### Browser/station scope

The one-user protection applies to the same browser profile because it relies on the secure Pruvs trusted-device cookie. A different browser, browser profile, or private/incognito context has an isolated cookie store and therefore looks like a separate device to a normal web application. Pruvs does not use invasive hardware/browser fingerprinting to try to correlate those isolated contexts.

## Install over v6.5

From the Git repository root (the directory that contains `backend`):

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\pruvs_v6_6_update.zip" -DestinationPath ".\backend" -Force
git add backend/app backend/tests backend/PRUVS_UPDATE_v6_6.md backend/FULL_APP_README.md backend/USER_FLOW_README.md
git commit -m "Pruvs v6.6 live split sync and browser account guard"
git push
```

Keep the current `.env`, database and uploaded receipts. No database reset or schema recreation is required.

## Verify after Render deploy

1. Open `/health` and confirm `version: 6.6.0`.
2. Open one split as two participants on two different devices/browsers. Select an item on device A. Device B should update automatically in about one second without pressing Save.
3. Use a receipt line with quantity 3. Let participant A take 1 and participant B take 2. Each view should show the participant names and quantities underneath the item.
4. On a third participant view, the fully allocated item should be grey and struck through.
5. Settle the bill, then reopen it as owner. Existing participant/quantity labels should still be present and editable again.
6. In one browser profile, open a split as user A, then authenticate user B in another tab. The older split tab should become blocked after the browser's active trusted account changes.

## Validation

`python -m pytest tests -q` completed with **63 passing tests** for this source tree.

The optional full NiceGUI page smoke script could not be executed in the packaging environment because the runtime there did not have the `nicegui` package installed; the modified Python modules themselves compile successfully and the service/API regression suite passes.
