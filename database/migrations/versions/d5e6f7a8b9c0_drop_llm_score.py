"""drop stale score from explore_pool

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('explore_pool') as batch_op:
        batch_op.drop_column('llm_' 'score')


def downgrade() -> None:
    with op.batch_alter_table('explore_pool') as batch_op:
        batch_op.add_column(sa.Column('llm_score', sa.Float(), nullable=True))
