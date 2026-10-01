# Pruvs v6.4 user flow

- Create an account with a unique username (a full name is allowed), email, contact phone and password. Activate it with email OTP.
- Sign in with username/email and password or a passkey. A new/expired/revoked browser requires email verification; a trusted browser does not show the routine OTP form.
- Verification codes appear in a separate dialog only when needed. Phone changes and account deletion are confirmed through email.
- Upload a picture/PDF, check the crop/preview and OCR, review items and totals, and create a shared bill.
- Other participants sign in and join with the shared link. The owner manages the bill from their account and is blocked from joining as another participant, with sign-out/account-switch options.
- Payment goes directly to the owner's saved Revolut or bank details. Pruvs coordinates the split.

Production setup, secrets to preserve and the new domain/passkey migration steps are in `PRUVS_DOMAIN_SETUP_v6_4.md`.
