"""add moderation_dismissals table

Revision ID: a7c4d29e6f18
Revises: f3d8b1a2c9e7
Create Date: 2026-08-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c4d29e6f18'
down_revision: Union[str, Sequence[str], None] = 'f3d8b1a2c9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('moderation_dismissals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('community_id', sa.Uuid(), nullable=False),
    sa.Column('section', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.String(length=64), nullable=False),
    sa.Column('metric_snapshot', sa.JSON(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('dismissed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['community_id'], ['communities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['dismissed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('community_id', 'section', 'target_id', name='uq_moderation_dismissal')
    )
    op.create_index(op.f('ix_moderation_dismissals_community_id'), 'moderation_dismissals', ['community_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_moderation_dismissals_community_id'), table_name='moderation_dismissals')
    op.drop_table('moderation_dismissals')
