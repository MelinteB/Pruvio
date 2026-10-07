# Pruvs v6.10 — Admin User API and API Collection Cleanup

## Summary

Pruvs v6.10 extends the administrator API and cleans the OpenAPI/Swagger collection without breaking the existing public URLs.

### Admin user management

All `/users` operations require the admin API key. The preferred request header is:

`X-Pruvs-Admin-Key: <admin key>`

The preferred Render variable is `PRUVS_ADMIN_API_KEY`. Existing installations using `PRUVIO_ADMIN_API_KEY` continue to work. The legacy request header `X-Pruvio-Admin-Key` is also accepted for compatibility, but is no longer advertised in Swagger.

Available admin endpoints:

- `GET /users/` — list/search/filter users (`status`, `email_verified`, `q`, `limit`, `offset`)
- `GET /users/stats` — counts by account state and email verification
- `GET /users/{user_id}` — retrieve one user
- `POST /users/` — create a user
- `PATCH /users/{user_id}` — edit an existing user without OTP or verified-email requirements
- `DELETE /users/{user_id}` — permanently delete a user without OTP

Example update:

```json
{
  "name": "Ana Popescu",
  "email": "ana@example.com",
  "status": "active",
  "is_email_verified": true,
  "preferred_language": "ro",
  "notifications_opt_in": true
}
```

Editable fields are limited to profile/contact/account-state/notification/payment information. `password_hash`, legal acceptance fields and internal timestamps cannot be edited through the admin API.

When an administrator changes an email or phone number, the related verification flag is reset to `false` unless `is_email_verified` or `is_phone_verified` is explicitly supplied in the same PATCH request.

## API collection cleanup

Swagger/OpenAPI is now ordered into:

1. System
2. Authentication
3. Registration
4. Receipts
5. Split Bill
6. Admin - Users
7. Admin - OpenAI

Browser-internal and compatibility endpoints remain operational but are hidden from `/docs`, including the signed browser receipt upload endpoint, short-link redirects and legacy deletion-OTP compatibility route. Legacy/internal routers continue to stay hidden.

The admin key is now represented as an API-key security scheme in Swagger, so the documented header is consistent across admin endpoints.

## Recommended API additions included

The following high-value, low-risk additions were made:

- single-user lookup
- partial user update
- user search/filter/pagination
- user statistics
- branded admin-key header with backwards compatibility

The release deliberately does **not** add direct password editing, arbitrary database-field editing, legal-consent overrides, or password/hash retrieval. Those operations create unnecessary security and audit risk.

## Existing APIs retained

- `/health`
- `/auth/*`
- `/onboarding/otp/*`
- `/app/receipts*`
- `/split-bill/*`
- `/openai/status`
- `/openai/receipts/{document_id}/process`
- `/openai/translate`

## Version

Application/OpenAPI/PWA cache version: `6.10.0`.
