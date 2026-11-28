"""Safely remove long-abandoned, unlinked campaign media from Business R2.

Dry-run is the default. Only assets tracked by the additive v0.6.25 registry,
unlinked to a promotion, and older than the minimum retention period qualify.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, inspect  # noqa: E402
from business.db import SessionLocal  # noqa: E402
from business.media_assets_v0725 import CampaignMediaAsset  # noqa: E402
from business.models import Promotion  # noqa: E402
from business.media_v067 import storage  # noqa: E402


MANAGED_KEY = re.compile(
    r'^campaigns/[^/]+/(?:sources|renders)/[a-f0-9]{32}\.(?:jpg|png|gif|mp4)$'
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--older-than-days', type=int, default=30,
                        help='Minimum age for unlinked assets (30 days or more; default 30).')
    parser.add_argument('--limit', type=int, default=250,
                        help='Maximum assets in this run (1–1000; default 250).')
    parser.add_argument('--apply', action='store_true',
                        help='Delete qualifying objects and registry rows; otherwise report only.')
    parser.add_argument('--confirm-bucket', default='',
                        help='Required with --apply; must match the configured bucket exactly.')
    args = parser.parse_args()
    if args.older_than_days < 30:
        parser.error('--older-than-days must be at least 30.')
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be between 1 and 1000.')
    if args.apply and not args.confirm_bucket:
        parser.error('--confirm-bucket is required with --apply.')
    if not args.apply and args.confirm_bucket:
        parser.error('--confirm-bucket is only valid with --apply.')
    return args


def main():
    args = parse_args()
    client, cfg = storage()
    bucket = cfg['PRUVS_CAMPAIGN_R2_BUCKET']
    if args.apply and args.confirm_bucket != bucket:
        raise SystemExit('Bucket confirmation does not match campaign storage configuration.')
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)
    session_factory = SessionLocal()
    deleted = 0
    scanned = 0
    with session_factory() as db:
        if db.get_bind().dialect.name != 'postgresql':
            raise SystemExit('This cleanup is limited to the PostgreSQL Business database.')
        protected = set(db.scalars(select(CampaignMediaAsset.media_key).where(
            CampaignMediaAsset.promotion_id.is_not(None),
        )).all())
        public_base_path = urlsplit(cfg['PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL']).path.rstrip('/')
        for media_url in db.scalars(select(Promotion.media_url)).all():
            if media_url:
                raw_path = unquote(urlsplit(media_url).path)
                path = raw_path[len(public_base_path):].lstrip('/') if public_base_path and raw_path.startswith(public_base_path + '/') else raw_path.lstrip('/')
                if MANAGED_KEY.fullmatch(path):
                    protected.add(path)
        gallery_table = 'loyalty_promotion_gallery_v0624'
        if inspect(db.get_bind()).has_table(gallery_table):
            from business.campaign_gallery_v0624 import CampaignGallery
            for assets_json in db.scalars(select(CampaignGallery.assets_json)).all():
                try:
                    for asset in json.loads(assets_json):
                        key = asset.get('media_key') if isinstance(asset, dict) else None
                        if isinstance(key, str) and MANAGED_KEY.fullmatch(key):
                            protected.add(key)
                except (TypeError, ValueError):
                    # A malformed gallery record is not permission to delete media.
                    continue
        if not args.apply:
            query = (select(CampaignMediaAsset)
                     .where(CampaignMediaAsset.promotion_id.is_(None),
                            CampaignMediaAsset.created_at < cutoff)
                     .order_by(CampaignMediaAsset.created_at)
                     .limit(args.limit))
            rows = db.scalars(query).all()
            for row in rows:
                scanned += 1
                if not MANAGED_KEY.fullmatch(row.media_key):
                    print(f'SKIP invalid managed key: {row.media_key}')
                    continue
                if row.media_key in protected:
                    print(f'SKIP referenced media: {row.media_key}')
                    continue
                print(f'WOULD DELETE {row.media_key} (created {row.created_at.isoformat()})')
        else:
            seen_keys = set()
            while scanned < args.limit:
                conditions = [CampaignMediaAsset.promotion_id.is_(None),
                              CampaignMediaAsset.created_at < cutoff]
                if seen_keys:
                    conditions.append(CampaignMediaAsset.media_key.not_in(seen_keys))
                query = (select(CampaignMediaAsset).where(*conditions)
                         .order_by(CampaignMediaAsset.created_at).limit(1)
                         .with_for_update(skip_locked=True))
                row = db.scalar(query)
                if row is None:
                    break
                scanned += 1
                seen_keys.add(row.media_key)
                if not MANAGED_KEY.fullmatch(row.media_key):
                    print(f'SKIP invalid managed key: {row.media_key}')
                    db.rollback()
                    break
                if row.media_key in protected:
                    db.commit()
                    continue
                try:
                    client.delete_object(Bucket=bucket, Key=row.media_key)
                except Exception as exc:
                    db.rollback()
                    print(f'FAILED {row.media_key}: {type(exc).__name__}')
                    break
                db.delete(row)
                db.commit()
                deleted += 1
                print(f'DELETED {row.media_key}')
    print(f'Completed: scanned={scanned}, deleted={deleted}, mode={"apply" if args.apply else "dry-run"}')


if __name__ == '__main__':
    main()
