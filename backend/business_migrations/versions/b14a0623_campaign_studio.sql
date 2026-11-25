-- b14: Business staging only; additive; no existing rewards or programs changed.
BEGIN;
CREATE TABLE IF NOT EXISTS promotion_studio_v0623 (
 promotion_id VARCHAR(36) PRIMARY KEY REFERENCES loyalty_promotions(id) ON DELETE CASCADE,
 merchant_id VARCHAR(36) NOT NULL,
 source_keys_json TEXT NOT NULL DEFAULT '[]',
 restaurant_link VARCHAR(900) NOT NULL DEFAULT ''
);
COMMIT;
