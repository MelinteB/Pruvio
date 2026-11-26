"""Ordered campaign pictures; explicit additive migration, never DDL in HTTP."""
import json
from sqlalchemy import String, Text, ForeignKey, inspect
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException
from .db import Base
from .media_v067 import read_merchant_campaign_source, bucket_config, media_url

class CampaignGallery(Base):
    __tablename__ = 'loyalty_promotion_gallery_v0624'
    promotion_id: Mapped[str] = mapped_column(ForeignKey('loyalty_promotions.id'), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assets_json: Mapped[str] = mapped_column(Text, nullable=False)

def gallery_ready(db):
    return inspect(db.connection()).has_table(CampaignGallery.__tablename__)

def gallery_assets(db, promotion):
    if not gallery_ready(db):
        return []
    row = db.get(CampaignGallery, promotion.id)
    if not row or row.merchant_id != promotion.merchant_id:
        return []
    return json.loads(row.assets_json)

def validate_gallery(db, staff, keys, alt):
    if not keys:
        return []
    if not gallery_ready(db):
        raise HTTPException(503, 'Campaign gallery migration is not ready.')
    if len(keys) > 5 or len(set(keys)) != len(keys):
        raise HTTPException(422, 'Choose one to five distinct campaign pictures.')
    total = 0
    cfg = bucket_config()
    assets = []
    for key in keys:
        raw = read_merchant_campaign_source(staff, key)
        total += len(raw)
        if total > 12_000_000:
            raise HTTPException(413, 'Combined campaign pictures exceed the storage limit.')
        assets.append({'media_key':key,'media_url':media_url(cfg,key),
                       'media_type':'image/jpeg','media_alt':alt or ''})
    return assets

def save_gallery(db, promotion, assets):
    if not gallery_ready(db):
        if assets: raise HTTPException(503, 'Campaign gallery migration is not ready.')
        return
    row = db.get(CampaignGallery, promotion.id)
    if not assets:
        if row: db.delete(row)
        return
    if not row:
        row = CampaignGallery(promotion_id=promotion.id, merchant_id=promotion.merchant_id, assets_json='[]')
        db.add(row)
    if row.merchant_id != promotion.merchant_id:
        raise HTTPException(409, 'Campaign gallery ownership mismatch.')
    row.assets_json = json.dumps(assets, ensure_ascii=False)
