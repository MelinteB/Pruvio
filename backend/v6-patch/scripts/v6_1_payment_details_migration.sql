-- Pruvio v6.1 idempotent PostgreSQL compatibility migration
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_recipient_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_iban VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_bank_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_bic VARCHAR(32);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_note VARCHAR(255);
