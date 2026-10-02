# Pruvs v6.5 user flow

- Create an account with first name, surname, email, contact phone and password. Pruvs derives a unique username such as `ana.popescu`, then activates the account with email OTP.
- Sign in with username/email and password or a passkey. A new/expired/revoked browser requires email verification; a trusted browser does not show the routine OTP form.
- Upload a picture/PDF, check the crop/preview and OCR, review items and totals, and create a shared bill.
- Other signed-in participants join with the shared link. Multi-quantity lines stay available until every unit is assigned, and the screen shows what remains to split.
- A percentage tip is based on each person's own split amount. Fixed tips are divided equally.
- History keeps both open and settled split bills for every account involved and identifies each entry as Owner or Participant.
- Only the owner can settle or reopen a settled bill. Reopening keeps allocations but resets payment statuses so amounts can be recalculated safely.
- Payment goes directly to the owner's saved Revolut or bank details. Pruvs coordinates the split and does not receive the money.

See `PRUVS_UPDATE_v6_5.md` for this release and `PRUVS_DOMAIN_SETUP_v6_4.md` for the existing production domain/provider configuration.
