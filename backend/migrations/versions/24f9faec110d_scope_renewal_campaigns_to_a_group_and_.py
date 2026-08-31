"""scope renewal campaigns to a group and track removal

Revision ID: 24f9faec110d
Revises: 53f06bd899a1
Create Date: 2026-08-31 18:25:17.612481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24f9faec110d'
down_revision: Union[str, Sequence[str], None] = '53f06bd899a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Drops and recreates both renewal tables rather than ALTERing in place —
    SQLite can't ALTER a foreign key, and per this feature's plan, no
    campaign data predates group-scoped renewals is expected to survive this
    change (renewals are a very new feature; any existing rows are
    early-stage test data, not something this migration needs to preserve).
    """
    op.drop_table('renewal_confirmations')
    op.drop_table('renewal_campaigns')

    op.create_table(
        'renewal_campaigns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('group_id', sa.Uuid(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_renewal_campaigns_group_id'), 'renewal_campaigns', ['group_id'], unique=False)

    op.create_table(
        'renewal_confirmations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_message_id', sa.String(length=128), nullable=True),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['renewal_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'member_id', name='uq_renewal_confirmation'),
    )
    op.create_index(
        op.f('ix_renewal_confirmations_campaign_id'), 'renewal_confirmations', ['campaign_id'], unique=False
    )
    op.create_index(
        op.f('ix_renewal_confirmations_member_id'), 'renewal_confirmations', ['member_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('renewal_confirmations')
    op.drop_table('renewal_campaigns')

    op.create_table(
        'renewal_campaigns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('community_id', sa.Uuid(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['community_id'], ['communities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_renewal_campaigns_community_id'), 'renewal_campaigns', ['community_id'], unique=False)

    op.create_table(
        'renewal_confirmations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_message_id', sa.String(length=128), nullable=True),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['renewal_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'member_id', name='uq_renewal_confirmation'),
    )
    op.create_index(
        op.f('ix_renewal_confirmations_campaign_id'), 'renewal_confirmations', ['campaign_id'], unique=False
    )
    op.create_index(
        op.f('ix_renewal_confirmations_member_id'), 'renewal_confirmations', ['member_id'], unique=False
    )
