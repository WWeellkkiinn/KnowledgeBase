"""add explore pool

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'explore_pool',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=True),
        sa.Column('raw_metadata_json', sa.JSON(), nullable=True),
        sa.Column('action', sa.String(length=16), nullable=True),
        sa.Column('acted_at', sa.DateTime(), nullable=True),
        sa.Column('found_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('llm_score', sa.Float(), nullable=True),
        sa.Column('llm_reason', sa.Text(), nullable=True),
        sa.Column('scored_at', sa.DateTime(), nullable=True),
        sa.Column('title_zh', sa.Text(), nullable=True),
        sa.Column('tags_json', sa.JSON(), nullable=True),
        sa.Column('research_question', sa.Text(), nullable=True),
        sa.Column('methodology', sa.Text(), nullable=True),
        sa.Column('key_findings_json', sa.JSON(), nullable=True),
        sa.Column('embedding', sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_explore_pool_subscription_id', 'explore_pool', ['subscription_id'], unique=False)
    op.create_index('ix_explore_pool_action', 'explore_pool', ['action'], unique=False)


def downgrade():
    op.drop_table('explore_pool')
