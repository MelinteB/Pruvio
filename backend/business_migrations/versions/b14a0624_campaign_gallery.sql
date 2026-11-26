-- Business database ONLY. Additive migration; take backup and verify environment.
BEGIN;
CREATE TABLE IF NOT EXISTS loyalty_promotion_gallery_v0624 (
    promotion_id VARCHAR(36) PRIMARY KEY REFERENCES loyalty_promotions(id),
    merchant_id VARCHAR(36) NOT NULL,
    assets_json TEXT NOT NULL
);
COMMIT;
-- Rollback application first; leave additive table intact to preserve saved galleries.
-- SELECT to_regclass('public.loyalty_promotion_gallery_v0624');
