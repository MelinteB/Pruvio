# Pruvio v6.3 user flow

## New account

1. Enter full name, available unique username, email, contact phone and password.
2. Review Terms and Privacy, then accept them.
3. Create account; verify the email code in the popup.
4. The account becomes active and the browser is remembered. Account settings can add a passkey.

## Returning user

Sign in with username or email and a password, or use a passkey. A new/untrusted browser requires an email OTP popup. On a remembered browser, the OTP option is hidden. Forgotten passwords are reset using an email confirmation popup.

## Receipt and shared bill

Upload an image/PDF → review extracted items → start split → share the participant link.

Other users sign in, join and select their quantities. When the owner opens the shared link, Pruvio explains that the link is for other users and offers sign-out/account switching. Account switching returns to the bill after sign-in. The owner manages the bill from their own receipt/history page.

## Account

Full name and unique username can be edited separately. A new email is confirmed at the new address; phone changes are confirmed at the existing verified email. Account deletion requires an email OTP with an explicit permanent-deletion confirmation. OTP inputs appear only inside the requested popup.

See [EMAIL_OTP_SETUP_v6_3.md](EMAIL_OTP_SETUP_v6_3.md) for deployment and validation.
