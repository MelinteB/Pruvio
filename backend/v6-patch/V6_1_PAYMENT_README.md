# Pruvio v6.1 — direct-to-owner payment details

- Removed Google Pay and Apple Pay checkout options from the split flow.
- The owner can save bank-transfer details and/or a Revolut.me link in Account → Payment details.
- Saved bank details: recipient name, IBAN, bank name, BIC/SWIFT and an optional default reference/note.
- These details are shown to participants only after the split is settled.
- Participants can copy payment fields, open the owner's Revolut link, and mark their payment as paid.
- Pruvio does not receive, hold or redirect the payment.
- Card number, expiry date, PIN and CVV must never be entered or stored.
- Compatibility migration adds the new payment-detail columns automatically at startup.
