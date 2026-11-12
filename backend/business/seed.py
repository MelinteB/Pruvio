"""Development seed only. Production onboarding requires verified merchant approval."""
from sqlalchemy import select
from .db import SessionLocal
from .models import Merchant, Staff, Store, Program
from .security import hasher
from .config import get_settings

def seed():
    cfg=get_settings()
    if cfg.app_env != 'development':raise RuntimeError('Seed is development-only')
    if len(cfg.demo_merchant_password)<12:raise RuntimeError('Set DEMO_MERCHANT_PASSWORD (12+ chars) in .env')
    with SessionLocal()() as db:
        exists=db.scalar(select(Staff).where(Staff.email==cfg.demo_merchant_email.lower()))
        if exists:
            print('Development merchant already exists');return
        m=Merchant(name='Demo Bistro')
        db.add(m);db.flush()
        user=Staff(merchant_id=m.id,email=cfg.demo_merchant_email.lower(),
                   password_hash=hasher.hash(cfg.demo_merchant_password),role='owner')
        s=Store(merchant_id=m.id,name='Demo Bistro — Central',address='Demo location, Bucharest',latitude=44.4268,longitude=26.1025)
        db.add_all([user,s]);db.flush()
        db.add(Program(merchant_id=m.id,store_id=s.id,title='Lunch Rewards',description='Every 3 qualifying receipts earn a 20 RON voucher.',
                       stamps_required=3,min_purchase_minor=3000,reward_minor=2000,status='published'))
        db.commit()
        print('Created development merchant, store and published loyalty program')

if __name__=='__main__':seed()
