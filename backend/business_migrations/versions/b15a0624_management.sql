-- Business database ONLY; additive, no customer records changed.
BEGIN;
CREATE TABLE IF NOT EXISTS merchant_location_archives_v0624 (
 store_id VARCHAR(36) PRIMARY KEY REFERENCES stores(id),
 merchant_id VARCHAR(36) NOT NULL,
 archived_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE TABLE IF NOT EXISTS merchant_management_audit_v0624 (
 id VARCHAR(36) PRIMARY KEY,
 merchant_id VARCHAR(36) NOT NULL,
 actor_id VARCHAR(36) NOT NULL,
 object_type VARCHAR(20) NOT NULL,
 object_id VARCHAR(36) NOT NULL,
 action VARCHAR(32) NOT NULL,
 details TEXT NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_merchant_management_audit_v0624_merchant_id ON merchant_management_audit_v0624(merchant_id);
COMMIT;
