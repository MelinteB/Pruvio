-- Pruvio v6 idempotent PostgreSQL compatibility migration
ALTER TABLE users ADD COLUMN IF NOT EXISTS revolut_payment_link VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_recipient_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_iban VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_bank_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_bic VARCHAR(32);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_note VARCHAR(255);
ALTER TABLE split_bill_sessions ADD COLUMN IF NOT EXISTS tip_mode VARCHAR(20) DEFAULT 'none';
ALTER TABLE split_bill_sessions ADD COLUMN IF NOT EXISTS tip_value DOUBLE PRECISION DEFAULT 0;
ALTER TABLE split_bill_sessions ADD COLUMN IF NOT EXISTS settled_at TIMESTAMP NULL;
ALTER TABLE split_bill_participants ADD COLUMN IF NOT EXISTS reminder_message VARCHAR(500);
ALTER TABLE split_bill_participants ADD COLUMN IF NOT EXISTS reminder_at TIMESTAMP NULL;
ALTER TABLE split_bill_participants ADD COLUMN IF NOT EXISTS payment_status VARCHAR(30) DEFAULT 'unpaid';
ALTER TABLE split_bill_participants ADD COLUMN IF NOT EXISTS payment_method VARCHAR(40);
ALTER TABLE split_bill_participants ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP NULL;
