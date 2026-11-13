"""One-time manual provisioning of a platform pilot operator in isolated staging.

This intentionally does NOT run during deployment, migration or app startup.
It will not promote an existing merchant staff account.
"""
import argparse
import getpass
import re
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from argon2 import PasswordHasher

from business.config import get_settings
from business.db import engine
from business.models import Merchant, Staff


def validate_staging_url(url):
    return (url.database == 'pruvs_business_staging'
            and url.username == 'pruvs_business_stage')


def main():
    parser=argparse.ArgumentParser(description='Staging-only Pruvs pilot platform administrator')
    parser.add_argument('--email',required=True,help='Dedicated staging platform operator email')
    parser.add_argument('--confirm-staging',action='store_true')
    options=parser.parse_args()
    if not options.confirm_staging:
        raise SystemExit('STOP: pass --confirm-staging after verifying the target database')
    email=options.email.strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
        raise SystemExit('STOP: invalid operator email')
    url=make_url(get_settings().database_url)
    if not validate_staging_url(url):
        raise SystemExit('STOP: must target pruvs_business_staging with pruvs_business_stage role')
    password=getpass.getpass('New dedicated STAGING operator password (20+ chars): ')
    confirm=getpass.getpass('Repeat operator password: ')
    if len(password)<20 or password!=confirm:
        raise SystemExit('STOP: password too short or confirmation mismatch')
    phrase=input('Type CREATE STAGING PLATFORM ADMIN to continue: ').strip()
    if phrase!='CREATE STAGING PLATFORM ADMIN':
        raise SystemExit('STOP: provisioning canceled')
    with Session(engine()) as db:
        if db.scalar(select(Staff.id).where(Staff.email==email)):
            raise SystemExit('STOP: email already used; existing staff accounts will not be promoted')
        ops=db.scalar(select(Merchant).where(
            Merchant.name=='Pruvs Platform Operations (staging)'))
        if ops is None:
            ops=Merchant(name='Pruvs Platform Operations (staging)',status='active')
            db.add(ops);db.flush()
        operator=Staff(merchant_id=ops.id,email=email,
                       password_hash=PasswordHasher().hash(password),
                       role='platform_admin',active=True)
        db.add(operator)
        db.commit()
    print('Created a dedicated staging platform administrator. Do not share its credentials.')


if __name__=='__main__':
    main()
