"""Opt-in merchant pilot permissions, tracked by platform-admin decisions.

Alembic revision: b11a0612pilot
Revision branch: existing b10d067discount
Additive only. Does not grant pilot access to any existing merchant.
"""
from alembic import op
import sqlalchemy as sa

revision='b11a0612pilot'
down_revision='b10d067discount'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table(
        'merchant_pilot_enrollment_v0612',
        sa.Column('merchant_id',sa.String(36),sa.ForeignKey('merchants.id'),primary_key=True),
        sa.Column('status',sa.String(24),nullable=False),
        sa.Column('requested_by_staff_id',sa.String(36),sa.ForeignKey('merchant_staff.id'),nullable=True),
        sa.Column('reviewed_by_staff_id',sa.String(36),sa.ForeignKey('merchant_staff.id'),nullable=True),
        sa.Column('requested_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('reviewed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("status IN ('requested','approved','denied','revoked')",
                           name='ck_pilot_enrollment_status_v0612'),
    )
    op.create_index('ix_pilot_enrollment_status_v0612',
                    'merchant_pilot_enrollment_v0612',['status'])
    op.create_table(
        'merchant_pilot_audit_v0612',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('merchant_id',sa.String(36),sa.ForeignKey('merchants.id'),nullable=False),
        sa.Column('actor_staff_id',sa.String(36),sa.ForeignKey('merchant_staff.id'),nullable=False),
        sa.Column('action',sa.String(24),nullable=False),
        sa.Column('old_status',sa.String(24),nullable=False),
        sa.Column('new_status',sa.String(24),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index('ix_pilot_audit_merchant_v0612',
                    'merchant_pilot_audit_v0612',['merchant_id'])


def downgrade():
    raise RuntimeError('Pilot decision history must not be deleted by an automatic downgrade')
