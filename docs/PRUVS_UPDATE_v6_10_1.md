# Pruvs v6.10.1 — Admin user PATCH hotfix

Fixes false HTTP 409 conflicts when an administrator PATCHes an existing user
and includes the user's current username, email, or phone number.

PATCH is now idempotent for unchanged unique fields. Uniqueness checks run only
when the normalized value actually changes.

Swagger also documents HTTP 409 for the admin user edit endpoint.
