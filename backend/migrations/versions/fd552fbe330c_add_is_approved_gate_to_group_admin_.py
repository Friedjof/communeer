"""add is_approved gate to group admin claim flow

Revision ID: fd552fbe330c
Revises: 92ca92d39bfa
Create Date: 2026-09-01 17:06:36.379099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd552fbe330c'
down_revision: Union[str, Sequence[str], None] = '92ca92d39bfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `server_default` required (not just at the ORM level) — same SQLite
    # "can't add a NOT NULL column with no default to a populated table"
    # reasoning as `is_claimed`'s own migration. Every pre-existing row
    # (owner/admin/viewer, and any already-claimed group_admin) backfills to
    # `True` ("already fine, unaffected by this feature").
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_approved', sa.Boolean(), nullable=False, server_default=sa.true()))

    # An already-auto-provisioned-but-still-unclaimed `group_admin` account
    # went through the *old* automatic-send behavior this feature replaces —
    # grandfather it back to "needs approval" rather than silently trusting
    # the server_default above, so every such account gets a fresh, explicit
    # owner decision under the new regime instead of skipping it.
    op.execute(
        "UPDATE users SET is_approved = 0 WHERE role = 'group_admin' AND is_claimed = 0"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_approved')
