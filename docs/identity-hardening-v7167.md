# Core 7.1.67 staging identity hardening
- LinkedIn confidential code exchange: no nonce requested; missing nonce accepted only for LinkedIn. Existing browser-bound state, JWT signature/issuer/audience/expiry, and UserInfo subject validation retained. Confirm real account and review injection/replay protections before production.
- Verified email collision routes to existing sign-in; no automatic account linking. PostgreSQL advisory lock serializes normal and social email creation; full uniqueness audit and DB constraint remain separate.
- Facebook/TikTok start/callback diagnostics and access-log query redaction. Render edge/request logs are outside this filter.
- Direct passkey signup: flag PASSKEY_SIGNUP_ENABLED defaults false. Browser-bound email OTP, profile binding, one-use WebAuthn challenge, atomic credential/account activation. Restart after cancellation; iOS device and integration tests required.
- Meta public /data-deletion instructions and signed /api/v1/auth/social/facebook/deauthorize; no automated full-account deletion callback. Existing authenticated account deletion stays authoritative. Review Meta dashboard and privacy obligations before public launch.
- Facebook/TikTok actual sandbox login and TikTok video require provider test users/consent. No real sign-in claimed.
