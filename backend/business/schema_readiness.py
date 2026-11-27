"""Read-only staging schema checks for v0.6.6, independent of migration execution."""
from sqlalchemy import inspect

REQUIRED_MEDIA_COLUMNS=frozenset(('media_url','media_type','media_alt'))
REQUIRED_CODE_TABLE='loyalty_customer_claim_codes_v12'

def check_schema(bind):
    inspector=inspect(bind)
    if not inspector.has_table('loyalty_promotions'):
        return {'campaign_media':False,'campaign_media_registry':False,
                'customer_codes':False,'discount_reconciliation':False,
                'program_scoped_pilot_approval':False}
    columns={c['name'] for c in inspector.get_columns('loyalty_promotions')}
    return {'campaign_media':REQUIRED_MEDIA_COLUMNS.issubset(columns),
            'campaign_media_registry':inspector.has_table('loyalty_campaign_media_v0725'),
            'customer_codes':inspector.has_table(REQUIRED_CODE_TABLE),
            'discount_reconciliation':inspector.has_table('loyalty_discount_reconciliation_v067')
              and inspector.has_table('loyalty_rewards')
              and 'source_claim_id' in {c['name'] for c in inspector.get_columns('loyalty_rewards')},
            'program_scoped_pilot_approval':inspector.has_table('merchant_program_pilot_enrollment_v0726')
              and inspector.has_table('merchant_program_pilot_audit_v0726')}
