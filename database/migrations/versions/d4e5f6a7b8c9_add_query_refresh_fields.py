"""add query_refreshed_at and query_stats_json to subscriptions

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('subscriptions', sa.Column('query_refreshed_at', sa.DateTime(), nullable=True))
    op.add_column('subscriptions', sa.Column('query_stats_json', sa.JSON(), nullable=True))

def downgrade():
    op.drop_column('subscriptions', 'query_stats_json')
    op.drop_column('subscriptions', 'query_refreshed_at')
