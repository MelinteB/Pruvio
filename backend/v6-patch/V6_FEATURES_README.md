# Pruvio v6

## Highlights
- Admin deletion is `DELETE /users/{user_id}` and requires `X-Pruvio-Admin-Key`. No OTP is used on the admin endpoint. Self-service account deletion in the UI remains OTP protected.
- Shared split links require a Pruvio login. New users can register and return to the shared bill.
- Split items update across active links every second; selections already claimed by others are greyed/crossed and labelled with participant names.
- Owner can set a percent or fixed tip. Tip is shared equally by every joined participant, including the owner.
- Once the split is settled, participants see only the owner's saved direct-payment details: bank transfer data and/or a Revolut.me link. Pruvio does not route money through another merchant or platform account.
- On mobile, the owner can open SMS/WhatsApp reminders from the device. Pruvio in-app reminders are available on all devices.
- Receipt upload now uses a scanner-style crop workspace: draggable crop frame, move, rotate, zoom and reset; only the exact cropped image is submitted to OCR.
- UI shell/logo were refreshed with a cleaner professional design.

## Direct-to-owner payments
Owners can save beneficiary name, IBAN, bank name, BIC/SWIFT, a payment note and/or a Revolut.me link in Account → Payment details. Card number, expiry, PIN and CVV must never be stored in Pruvio.

## Admin delete example
```bash
curl -X DELETE \
  -H "X-Pruvio-Admin-Key: $PRUVIO_ADMIN_API_KEY" \
  https://pruvio.onrender.com/users/123
```

## Database
Compatibility migration runs on startup. The optional SQL file is `scripts/v6_split_and_profile_migration.sql`.
