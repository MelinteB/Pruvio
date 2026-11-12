"""Inspect Business staging schema only; does not modify any database.

Run from the backend working directory with Business *staging* environment.
"""
from sqlalchemy.engine import make_url
from business.config import get_settings
from business.db import engine
from business.schema_readiness import check_schema

def main():
    settings=get_settings()
    url=make_url(settings.database_url)
    if url.database!='pruvs_business_staging' or url.username!='pruvs_business_stage':
        raise SystemExit('STOP: expected pruvs_business_staging and pruvs_business_stage')
    flags=check_schema(engine())
    print('Target verified: pruvs_business_staging')
    for name,value in flags.items():
        print(('PASS' if value else 'MISSING')+': '+name)
    if not all(flags.values()):
        print('Migration incomplete. Back up staging database before running Alembic upgrades.')
        return 2
    print('PASS: Business v0.6.6 staging schema is ready')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
