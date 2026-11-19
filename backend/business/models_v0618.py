"""A merchant-owned link to a Google place; do NOT cache Places data.

Google Place IDs are storage-exempt. All names, ratings, review excerpts and
attributions from Google are fetched live, never persisted in this table.
"""
from sqlalchemy import DateTime,ForeignKey,String
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import utcnow

class MerchantStorePlace(Base):
    __tablename__='merchant_store_google_place_v0618'
    store_id:Mapped[str]=mapped_column(ForeignKey('stores.id'),primary_key=True)
    merchant_id:Mapped[str]=mapped_column(ForeignKey('merchants.id'),nullable=False,index=True)
    place_id:Mapped[str]=mapped_column(String(255),nullable=False)
    linked_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
