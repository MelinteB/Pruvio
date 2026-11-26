-- Business database only. Additive ownership index; does not alter campaign or customer data.
BEGIN;
CREATE TABLE IF NOT EXISTS loyalty_campaign_media_v0725 (
    media_key VARCHAR(500) PRIMARY KEY,
    merchant_id VARCHAR(36) NOT NULL,
    asset_kind VARCHAR(16) NOT NULL CHECK (asset_kind IN ('source','render')),
    promotion_id VARCHAR(36) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_campaign_media_v0725_merchant
    ON loyalty_campaign_media_v0725(merchant_id);
CREATE INDEX IF NOT EXISTS ix_campaign_media_v0725_promotion
    ON loyalty_campaign_media_v0725(promotion_id);
COMMIT;
-- Roll back application code first. Keep this table and its rows during routine rollback.
