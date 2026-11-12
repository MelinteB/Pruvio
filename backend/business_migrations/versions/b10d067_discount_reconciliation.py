"""Pruvs Business v0.6.7 merchant-attested discount reconciliation; additive, no destructive downgrade."""
from alembic import op
import sqlalchemy as sa
revision='b10d067discount'
down_revision='b09c0149codes'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('loyalty_rewards',
      sa.Column('source_claim_id',sa.String(36),sa.ForeignKey('receipt_claims.id'),nullable=True))
    op.create_index('ix_loyalty_rewards_source_claim_id','loyalty_rewards',['source_claim_id'])
    op.create_table('loyalty_discount_reconciliation_v067',
      sa.Column('id',sa.String(36),primary_key=True),
      sa.Column('reward_id',sa.String(36),sa.ForeignKey('loyalty_rewards.id'),nullable=False,unique=True),
      sa.Column('merchant_id',sa.String(36),sa.ForeignKey('merchants.id'),nullable=False),
      sa.Column('program_id',sa.String(36),sa.ForeignKey('loyalty_programs.id'),nullable=False),
      sa.Column('source_claim_id',sa.String(36),sa.ForeignKey('receipt_claims.id'),nullable=True),
      sa.Column('consumer_id',sa.String(100),nullable=False),
      sa.Column('staff_id',sa.String(36),sa.ForeignKey('merchant_staff.id'),nullable=False),
      sa.Column('sale_reference',sa.String(120),nullable=False),
      sa.Column('sale_amount_minor',sa.Integer(),nullable=False),
      sa.Column('discount_minor',sa.Integer(),nullable=False),
      sa.Column('currency',sa.String(3),nullable=False),
      sa.Column('verification_source',sa.String(32),nullable=False),
      sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_discount_reconciliation_v067_merchant','loyalty_discount_reconciliation_v067',['merchant_id'])
    op.create_index('ix_discount_reconciliation_v067_customer','loyalty_discount_reconciliation_v067',['consumer_id'])
    op.create_index('ix_discount_reconciliation_v067_reward','loyalty_discount_reconciliation_v067',['reward_id'],unique=True)
def downgrade():
    raise RuntimeError('Destructive audit migration downgrade intentionally disabled')
