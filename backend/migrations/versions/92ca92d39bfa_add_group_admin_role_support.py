"""add group admin role support

Revision ID: 92ca92d39bfa
Revises: 888a09278a67
Create Date: 2026-09-01 01:48:26.102093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92ca92d39bfa'
down_revision: Union[str, Sequence[str], None] = '888a09278a67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `batch_alter_table` (recreate-and-copy under SQLite, plain ALTER under
    # Postgres) is required here — this is the first migration in this repo
    # that adds a foreign key to an *already-existing* table (every prior FK
    # was declared inline on a brand-new `op.create_table`), and SQLite has
    # no native `ALTER TABLE ... ADD CONSTRAINT`.
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('member_id', sa.Uuid(), nullable=True))
        # `server_default` required here (not just at the ORM level) — same
        # SQLite "can't add a NOT NULL column with no default to a
        # populated table" reasoning as `totp_enabled`/`whatsapp_otp_enabled`'s
        # own migrations. Every pre-existing row (owner/admin/viewer)
        # backfills to `True` ("already claimed", unaffected by this feature).
        batch_op.add_column(sa.Column('is_claimed', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_member_id'), ['member_id'], unique=True)
        batch_op.create_foreign_key(
            'fk_users_member_id_members', 'members', ['member_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('fk_users_member_id_members', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_member_id'))
        batch_op.drop_column('claimed_at')
        batch_op.drop_column('is_claimed')
        batch_op.drop_column('member_id')
