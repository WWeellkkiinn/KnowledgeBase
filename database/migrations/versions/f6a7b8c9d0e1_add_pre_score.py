"""add pre_score to explore_pool

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('explore_pool', sa.Column('pre_score', sa.Float(), nullable=True))
    op.create_index('ix_explore_pool_pre_score', 'explore_pool', ['pre_score'])


def downgrade() -> None:
    op.drop_index('ix_explore_pool_pre_score', table_name='explore_pool')
    op.drop_column('explore_pool', 'pre_score')
