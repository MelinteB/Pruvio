# Pruvs v6.6 user flow

## Split bill

```text
Owner scans/uploads receipt
→ OCR/review
→ starts split bill
→ shares invitation
→ participants sign in
→ selecting/unselecting quantities saves immediately
→ all open participants receive near-real-time updates
→ each item shows participant names + selected quantities
→ fully claimed items are grey/struck for users who have no share in them
→ owner settles bill
→ split remains in owner and participant history
→ owner may reopen; allocations stay visible and editable, payment state resets
```

Percentage tips are calculated from each person's own item total, including the owner.

A split page is bound to the Pruvs account represented by the current trusted-device cookie. If the same browser profile switches to another Pruvs account, the older split page is blocked rather than allowing two different users to operate simultaneously in that browser session.

## Navigation

```text
Home · Scan · History · Account
```

Existing email OTP, password/passkey, receipt OCR, history, payment-details and account flows remain unchanged.
