CREATE TABLE IF NOT EXISTS passkey_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id VARCHAR(1024) NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports VARCHAR(255),
    device_type VARCHAR(64),
    backed_up BOOLEAN NOT NULL DEFAULT FALSE,
    device_name VARCHAR(120),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS ix_passkey_credentials_user_id
    ON passkey_credentials(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_passkey_credentials_credential_id
    ON passkey_credentials(credential_id);
