"""Read-only Business b11 merchant enrollment schema gate for staging only."""
from sqlalchemy import inspect, select, func
from sqlalchemy.engine import make_url
from business.config import get_settings
from business.db import engine
from business.models import Staff
from business.models_v0612 import MerchantPilotEnrollment, MerchantPilotAudit


def main():
    url=make_url(get_settings().database_url)
    if url.database!='pruvs_business_staging' or url.username!='pruvs_business_stage':
        raise SystemExit('STOP: expected exact pruvs_business_staging / pruvs_business_stage')
    bind=engine()
    inspector=inspect(bind)
    names=(MerchantPilotEnrollment.__tablename__, MerchantPilotAudit.__tablename__)
    checks={name:inspector.has_table(name) for name in names}
    for table,passed in checks.items():
        print(('PASS' if passed else 'MISSING')+': '+table)
    if not all(checks.values()):
        print('STOP: inspect/review the additive Business b11 migration before enabling DB pilot mode.')
        return 2
    with bind.connect() as connection:
        admins=connection.scalar(select(func.count(Staff.id)).where(
            Staff.role=='platform_admin', Staff.active.is_(True)))
    print('Active platform operators available: '+str(admins))
    if not admins:
        print('No platform administrator exists; approval workflow is not yet usable.')
        return 3
    print('PASS: Business pilot enrollment schema and operator gate')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
