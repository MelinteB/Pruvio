# Pruvs v6.5 — split bill, history, username and branding update

Version endpoint after deployment: `/health` → `6.5.0`.

## Changes

- Multi-quantity receipt lines remain claimable by other participants until the full quantity is allocated. The split page shows the remaining quantity and remaining value for every item, plus the total still left to split.
- Duplicate receipt rows with the same product name are handled independently by receipt-item ID.
- Percentage tips are calculated for every person from that person's own assigned split value, including the owner. Fixed tips continue to be divided equally.
- History now keeps both open and settled split sessions for signed-in participants and owners. Every split is marked as **Owner** or **Participant**.
- A settled split can be reopened only by its owner. Existing allocations remain, while participant payment states are reset because the amounts may be changed after reopening.
- Registration now asks for first name and surname and automatically derives a username in the form `first.surname`. If it already exists, Pruvs adds `.2`, `.3`, and so on. Existing accounts and custom usernames remain unchanged.
- The Pruvs mark is now used for browser/PWA icons and Open Graph/Twitter share previews. Icon URLs and the service-worker cache are versioned to refresh older cached branding.
- A REST endpoint is available for owner reopening: `POST /split-bill/sessions/{token}/reopen` with `owner_user_id`.

## Deploy over the existing backend

Keep the current database, `.env`/Render environment variables, secrets and upload storage. Do **not** replace the database.

From the repository root on Windows PowerShell, unpack the update into the existing `backend` directory, then commit and push:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\pruvs_v6_5_update.zip" -DestinationPath ".\backend" -Force
git add backend
git commit -m "Pruvs v6.5 split history reopen tip and branding"
git push
```

For a clean source replacement, `pruvs_full_app_v6_5.zip` contains the complete backend without an `.env`, database, uploaded documents, caches or virtual environment.

## Checks after Render deploy

1. Open `/health` and confirm `version: 6.5.0`.
2. Create a receipt line with quantity 3. Let the owner take 1 and another participant take the remaining 2.
3. Set a 10% tip with unequal participant shares and confirm each person's tip is 10% of their own share.
4. Confirm History shows the same split for the owner as **Owner** and for the other account as **Participant**, while both open and settled bills remain listed.
5. Settle the bill, confirm only the owner sees **Reopen split**, reopen it, and confirm selections remain while payment status resets.
6. Register a new account and verify a name such as `Ana Popescu` produces `ana.popescu` (or the next free suffix).
7. Open a fresh/private browser and a newly shared bill link and confirm the Pruvs logo is used for the site icon/share preview. External apps may retain an older preview for an already-cached URL; new URLs should use the new metadata immediately.

Automated regression suite included with the package covers partial quantities, duplicate same-name rows, per-person percentage tips, history roles, owner-only reopening and automatic username derivation.
