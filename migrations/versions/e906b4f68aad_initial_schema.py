"""Initial schema

Revision ID: e906b4f68aad
Revises: 
Create Date: 2025-11-22 20:17:59.948899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e906b4f68aad'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create pgcrypto extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.UniqueConstraint('email')
    )
    
    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )
    
    # Create topics table
    op.create_table(
        'topics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kafka_topic_name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.UniqueConstraint('kafka_topic_name')
    )
    
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('secret_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    )
    
    # Create usage_counters table
    op.create_table(
        'usage_counters',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('messages_in', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('messages_out', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('bytes_in', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('bytes_out', sa.BigInteger(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'project_id', 'date', name='uq_user_project_date')
    )
    
    # Create global_usage_counters table
    op.create_table(
        'global_usage_counters',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('messages_in', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('bytes_in', sa.BigInteger(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date')
    )
    
    # Create indexes
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_projects_user_id', 'projects', ['user_id'])
    op.create_index('ix_topics_project_id', 'topics', ['project_id'])
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_usage_counters_user_id', 'usage_counters', ['user_id'])
    op.create_index('ix_usage_counters_project_id', 'usage_counters', ['project_id'])
    op.create_index('ix_usage_counters_date', 'usage_counters', ['date'])


def downgrade() -> None:
    op.drop_index('ix_usage_counters_date', table_name='usage_counters')
    op.drop_index('ix_usage_counters_project_id', table_name='usage_counters')
    op.drop_index('ix_usage_counters_user_id', table_name='usage_counters')
    op.drop_index('ix_api_keys_user_id', table_name='api_keys')
    op.drop_index('ix_topics_project_id', table_name='topics')
    op.drop_index('ix_projects_user_id', table_name='projects')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('global_usage_counters')
    op.drop_table('usage_counters')
    op.drop_table('api_keys')
    op.drop_table('topics')
    op.drop_table('projects')
    op.drop_table('users')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
