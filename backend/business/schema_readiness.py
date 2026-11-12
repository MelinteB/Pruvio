"""Read-only staging schema checks for v0.6.6, independent of migration execution."""
from sqlalchemy import inspect

REQUIRED_MEDIA_COLUMNS=frozenset(('media_url','media_type','media_alt'))
REQUIRED_CODE_TABLE='loyalty_customer_claim_codes_v12'

def check_schema(bind):
    inspector=inspect(bind)
    if not inspector.has_table('loyalty_promotions'):
        return {'campaign_media':False,'customer_codes':False}
    columns={c['name'] for c in inspector.get_columns('loyalty_promotions')}
    return {'campaign_media':REQUIRED_MEDIA_COLUMNS.issubset(columns),
            'customer_codes':inspector.has_table(REQUIRED_CODE_TABLE)}
