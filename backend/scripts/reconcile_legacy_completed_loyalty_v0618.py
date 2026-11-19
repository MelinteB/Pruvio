"""One-time, operator-driven cleanup for legacy redeemed vouchers on STAGING.

Dry-run by default. A completed membership is removable only if:
- zero stamps remain,
- a redeemed historical reward exists,
- no pending claims or available/reserved rewards exist.
The ledger, receipts, rewards, and merchant confirmations are never deleted.

IMPORTANT: run only once BEFORE customers start rejoining under v0.6.18;
a historical redeemed reward alone cannot distinguish an already-rejoined
zero-stamp account without an additional cycle-generation column.

Example after a verified staging backup:
    python scripts/reconcile_legacy_completed_loyalty_v0618.py
    python scripts/reconcile_legacy_completed_loyalty_v0618.py --apply --backup-id VERIFIED_BACKUP_ID
"""
import argparse
from sqlalchemy import select
from business.db import SessionLocal
from business.models import Membership, Reward
from business.loyalty_cycles_v0618 import close_completed_cycle
from business.config import get_settings


def reconcile(db, apply=False):
    total=0
    touched=0
    members=db.scalars(select(Membership).order_by(Membership.id)).all()
    for m in members:
        if m.stamps!=0:
            continue
        redeemed=db.scalar(select(Reward.id).where(
            Reward.consumer_id==m.consumer_id,
            Reward.program_id==m.program_id,
            Reward.status=='redeemed').limit(1))
        if redeemed is None:
            continue
        total+=1
        # Both dry-run and apply run the same locks and safety checks.
        if close_completed_cycle(db,consumer_id=m.consumer_id,program_id=m.program_id):
            touched+=1
        db.flush()
    if apply:
        db.commit()
    else:
        db.rollback()
    return {'completed_candidates':total,'eligible_memberships':touched,'applied':apply}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--backup-id',default='')
    opts=p.parse_args()
    if opts.apply:
        if get_settings().app_env not in ('staging','test'):
            raise SystemExit('Refusing destructive membership cleanup outside staging/test.')
        if len(opts.backup_id.strip())<8:
            raise SystemExit('A verified backup ID is required before --apply.')
    session=SessionLocal()()
    try:
        counts=reconcile(session,apply=opts.apply)
        print(f"Candidates: {counts['completed_candidates']}. "
              f"Eligible: {counts['eligible_memberships']}. Applied: {opts.apply}. "
              "Receipt and redemption audit ledgers unchanged.")
    finally:
        session.close()

if __name__=='__main__':
    main()
