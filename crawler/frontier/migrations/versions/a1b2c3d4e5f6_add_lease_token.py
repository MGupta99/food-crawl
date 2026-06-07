"""add lease_token fencing column to frontier_urls

Revision ID: a1b2c3d4e5f6
Revises: 92d812626a7d
Create Date: 2026-06-07 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '92d812626a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('frontier_urls', sa.Column('lease_token', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('frontier_urls') as batch_op:
        batch_op.drop_column('lease_token')
