"""Merchant-owned Places IDs only; Google reviews and addresses are NOT stored.

Revision b12a0618places; follows b11a0612pilot.
Additive, auditable and safe to run after a verified staging DB backup.
"""
from alembic import op
import sqlalchemy as sa

revision='b12a0618places'
down_revision='b11a0612pilot'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('merchant_store_google_place_v0618',
        sa.Column('store_id',sa.String(36),sa.ForeignKey('stores.id'),primary_key=True),
        sa.Column('merchant_id',sa.String(36),sa.ForeignKey('merchants.id'),nullable=False),
        sa.Column('place_id',sa.String(255),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_merchant_store_google_place_v0618_merchant',
      'merchant_store_google_place_v0618',['merchant_id'])

def downgrade():
    raise RuntimeError('Merchant place-link history is not deleted automatically')
