-- Pruvs Business b13: additive, reviewed prerequisite for account recovery
-- and tenant-scoped merchant staff management.
-- Execute ONLY against the Business PostgreSQL database, never Core.
-- Idempotent; no existing staff, passwords, users or claims are altered.

BEGIN;

CREATE TABLE IF NOT EXISTS merchant_signup_rates (
    bucket_hash VARCHAR(64) PRIMARY KEY,
    window_started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    attempts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS merchant_staff_actions_v1 (
    id VARCHAR(36) PRIMARY KEY,
    merchant_id VARCHAR(36) NOT NULL,
    actor_id VARCHAR(36) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    action VARCHAR(32) NOT NULL,
    before_role VARCHAR(20),
    after_role VARCHAR(20),
    before_active BOOLEAN,
    after_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_merchant_staff_actions_v1_merchant_id
ON merchant_staff_actions_v1(merchant_id);

COMMIT;

-- Read-only verification:
-- SELECT to_regclass('public.merchant_signup_rates'),
--        to_regclass('public.merchant_staff_actions_v1');
