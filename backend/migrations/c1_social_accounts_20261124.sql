-- Pruvs Core external identity migration; run on CORE DB, never Business DB.
-- Idempotent and non-destructive. Can be applied before deploying OAuth routes.
CREATE TABLE IF NOT EXISTS pruvs_social_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    connected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pruvs_social_provider_subject
    ON pruvs_social_accounts(provider, subject);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pruvs_social_user_provider
    ON pruvs_social_accounts(user_id, provider);
CREATE INDEX IF NOT EXISTS ix_pruvs_social_accounts_user_id
    ON pruvs_social_accounts(user_id);
