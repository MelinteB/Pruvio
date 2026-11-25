"""Persistent merchant-scoped campaign source selections (additive migration b14)."""
import json
from sqlalchemy import String,Text,ForeignKey,inspect
from sqlalchemy.orm import Mapped,mapped_column
from fastapi import HTTPException
from .db import Base
from .media_v067 import campaign_source_keys,bucket_config,media_url

class PromotionStudio(Base):
    __tablename__='promotion_studio_v0623'
    promotion_id:Mapped[str]=mapped_column(String(36),ForeignKey('loyalty_promotions.id',ondelete='CASCADE'),primary_key=True)
    merchant_id:Mapped[str]=mapped_column(String(36),nullable=False)
    source_keys_json:Mapped[str]=mapped_column(Text,nullable=False,default='[]')
    restaurant_link:Mapped[str]=mapped_column(String(900),nullable=False,default='')

def ready(db):
    return inspect(db.get_bind()).has_table(PromotionStudio.__tablename__)

def studio_data(db,promo):
    if not ready(db):return {'source_photos':[],'restaurant_link':''}
    row=db.get(PromotionStudio,promo.id)
    if not row or row.merchant_id!=promo.merchant_id:return {'source_photos':[],'restaurant_link':''}
    keys=json.loads(row.source_keys_json)
    photos=[]
    if keys:
        try:
            cfg=bucket_config()
            photos=[{'media_key':k,'media_url':media_url(cfg,k),'media_type':'image/jpeg'} for k in keys]
        except HTTPException:
            photos=[{'media_key':k,'media_url':'','media_type':'image/jpeg'} for k in keys]
    return {'source_photos':photos,'restaurant_link':row.restaurant_link}

def save_studio_data(db,staff,promo,keys,link):
    if keys is None and link is None:return
    if not ready(db):
        if keys or link:raise HTTPException(503,'Campaign source migration is not ready.')
        return
    row=db.get(PromotionStudio,promo.id)
    if row and row.merchant_id!=staff.merchant_id:raise HTTPException(403,'Campaign source ownership mismatch')
    if not row:
        row=PromotionStudio(promotion_id=promo.id,merchant_id=staff.merchant_id,source_keys_json='[]',restaurant_link='')
        db.add(row)
    if keys is not None:row.source_keys_json=json.dumps(campaign_source_keys(staff,None,keys))
    if link is not None:
        if link:
            from .website_import_v0623 import validate_url
            validate_url(link)
        row.restaurant_link=link
