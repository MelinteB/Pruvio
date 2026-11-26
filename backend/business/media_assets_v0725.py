"""Durable ownership records for campaign media and safe orphan collection."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import DateTime, String, inspect, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CampaignMediaAsset(Base):
    __tablename__ = 'loyalty_campaign_media_v0725'

    media_key: Mapped[str] = mapped_column(String(500), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    promotion_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


_MANAGED_KEY = re.compile(
    r'^campaigns/[^/]+/(?:sources|renders)/[a-f0-9]{32}\.(?:jpg|png|gif|mp4)$'
)


def media_registry_ready(db) -> bool:
    try:
        return inspect(db.connection()).has_table(CampaignMediaAsset.__tablename__)
    except Exception:
        return False


def _require_registry(db) -> None:
    if not media_registry_ready(db):
        raise HTTPException(503, 'Campaign media registry is not ready. Apply the reviewed additive migration.')


def register_media(db, merchant_id: str, media_key: str, asset_kind: str) -> None:
    _require_registry(db)
    if asset_kind not in ('source', 'render') or not _MANAGED_KEY.fullmatch(media_key):
        raise HTTPException(422, 'Campaign media key is invalid.')
    current = db.get(CampaignMediaAsset, media_key)
    if current and current.merchant_id != merchant_id:
        raise HTTPException(409, 'Campaign media ownership mismatch.')
    if current:
        if current.asset_kind != asset_kind:
            raise HTTPException(409, 'Campaign media type mismatch.')
        return
    db.add(CampaignMediaAsset(media_key=media_key, merchant_id=merchant_id,
                              asset_kind=asset_kind))
    db.commit()


def set_promotion_media(db, merchant_id: str, promotion_id: str,
                        media_keys: list[str]) -> None:
    """Associate only registered, merchant-owned new assets; retain legacy keys as-is."""
    managed = {key for key in media_keys if _MANAGED_KEY.fullmatch(key)}
    if managed:
        _require_registry(db)
    rows = db.scalars(select(CampaignMediaAsset).where(
        CampaignMediaAsset.promotion_id == promotion_id,
        CampaignMediaAsset.merchant_id == merchant_id,
    ).with_for_update()).all() if media_registry_ready(db) else []
    by_key = {row.media_key: row for row in rows}
    for key in managed:
        row = db.scalar(select(CampaignMediaAsset).where(
            CampaignMediaAsset.media_key == key,
        ).with_for_update())
        if row is None or row.merchant_id != merchant_id:
            raise HTTPException(422, 'Upload campaign pictures again before saving this draft.')
        if row.promotion_id not in (None, promotion_id):
            raise HTTPException(409, 'Campaign picture is already attached to another promotion.')
        row.promotion_id = promotion_id
        by_key.pop(key, None)
    for row in by_key.values():
        row.promotion_id = None
    if managed or rows:
        db.flush()


def promotion_media_assets(db, merchant_id: str, promotion_id: str) -> list[dict]:
    if not media_registry_ready(db):
        return []
    rows = db.scalars(select(CampaignMediaAsset).where(
        CampaignMediaAsset.promotion_id == promotion_id,
        CampaignMediaAsset.merchant_id == merchant_id,
    ).order_by(CampaignMediaAsset.asset_kind, CampaignMediaAsset.created_at)).all()
    return [{'media_key': row.media_key, 'asset_kind': row.asset_kind} for row in rows]
