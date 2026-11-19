"""Additive merchant Google Place ID linking table (no provider content persisted).

Revision ID: b12a0618place
Revises: b11a0612pilot

Apply with reviewed staging database backup first. Production remains unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision='b12a0618place'
down_revision='b11a0612pilot'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        'merchant_store_places_v0618',
        sa.Column('store_id',sa.String(36),sa.ForeignKey('stores.id'),primary_key=True),
        sa.Column('merchant_id',sa.String(36),sa.ForeignKey('merchants.id'),nullable=False),
        sa.Column('place_id',sa.String(260),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index('ix_store_places_merchant_v0618',
                    'merchant_store_places_v0618',['merchant_id'])

def downgrade():
    raise RuntimeError('Do not silently destroy merchant location associations')
