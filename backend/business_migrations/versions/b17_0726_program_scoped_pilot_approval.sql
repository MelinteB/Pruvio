-- Additive staging migration: approvals now target one exact loyalty program
-- and its location. Existing merchant-level audit records are retained.
CREATE TABLE merchant_program_pilot_enrollment_v0726 (
    program_id VARCHAR(36) PRIMARY KEY REFERENCES loyalty_programs(id),
    merchant_id VARCHAR(36) NOT NULL REFERENCES merchants(id),
    store_id VARCHAR(36) NOT NULL REFERENCES stores(id),
    status VARCHAR(24) NOT NULL DEFAULT 'requested',
    requested_by_staff_id VARCHAR(36) REFERENCES merchant_staff(id),
    reviewed_by_staff_id VARCHAR(36) REFERENCES merchant_staff(id),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_merchant_program_pilot_enrollment_v0726_merchant_id
    ON merchant_program_pilot_enrollment_v0726(merchant_id);
CREATE INDEX ix_merchant_program_pilot_enrollment_v0726_store_id
    ON merchant_program_pilot_enrollment_v0726(store_id);
CREATE TABLE merchant_program_pilot_audit_v0726 (
    id VARCHAR(36) PRIMARY KEY,
    program_id VARCHAR(36) NOT NULL REFERENCES loyalty_programs(id),
    merchant_id VARCHAR(36) NOT NULL REFERENCES merchants(id),
    store_id VARCHAR(36) NOT NULL REFERENCES stores(id),
    actor_staff_id VARCHAR(36) NOT NULL REFERENCES merchant_staff(id),
    action VARCHAR(24) NOT NULL,
    old_status VARCHAR(24) NOT NULL,
    new_status VARCHAR(24) NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_merchant_program_pilot_audit_v0726_program_id
    ON merchant_program_pilot_audit_v0726(program_id);
CREATE INDEX ix_merchant_program_pilot_audit_v0726_merchant_id
    ON merchant_program_pilot_audit_v0726(merchant_id);
