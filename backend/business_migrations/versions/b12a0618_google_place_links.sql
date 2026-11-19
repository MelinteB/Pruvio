-- Staging-only reviewed additive migration, execute AFTER verified backup.
-- Place IDs are retained; provider names, addresses, reviews, ratings are never cached.
-- Verify the active database first: SELECT current_database(), current_user;
BEGIN;
CREATE TABLE IF NOT EXISTS merchant_store_google_place_v0618 (
    store_id varchar(36) PRIMARY KEY REFERENCES stores(id),
    merchant_id varchar(36) NOT NULL REFERENCES merchants(id),
    place_id varchar(255) NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_merchant_store_google_place_v0618_merchant
    ON merchant_store_google_place_v0618 (merchant_id);
COMMIT;
-- Verify:
-- SELECT count(*) FROM merchant_store_google_place_v0618;
-- Production database changes are NOT authorized by this staging script.
