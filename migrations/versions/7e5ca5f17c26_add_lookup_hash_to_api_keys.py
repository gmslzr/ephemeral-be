"""add_lookup_hash_to_api_keys

Revision ID: 7e5ca5f17c26
Revises: e906b4f68aad
Create Date: 2025-11-22 22:32:32.811543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e5ca5f17c26'
down_revision: Union[str, None] = 'e906b4f68aad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add lookup_hash column (nullable initially for backward compatibility)
    op.add_column('api_keys', sa.Column('lookup_hash', sa.String(64), nullable=True))
    # Create index for fast O(1) lookup
    op.create_index('ix_api_keys_lookup_hash', 'api_keys', ['lookup_hash'])


def downgrade() -> None:
    op.drop_index('ix_api_keys_lookup_hash', table_name='api_keys')
    op.drop_column('api_keys', 'lookup_hash')
