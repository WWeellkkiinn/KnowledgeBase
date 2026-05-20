"""drop embedding add bandit

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-20 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('explore_pool') as batch_op:
        batch_op.drop_index('ix_explore_pool_pre_score')
        batch_op.drop_column('embedding')
        batch_op.drop_column('pre_score')

    with op.batch_alter_table('tag_dict') as batch_op:
        batch_op.add_column(sa.Column('alpha', sa.Float(), nullable=False, server_default='0.5'))
        batch_op.add_column(sa.Column('beta', sa.Float(), nullable=False, server_default='0.5'))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE tag_dict
               SET alpha = 0.5 + COALESCE((
                     SELECT COUNT(DISTINCT ep.id)
                       FROM explore_pool ep, json_each(ep.tags_json) je
                      WHERE ep.action = 'saved' AND je.value = tag_dict.tag
                   ), 0),
                   beta = 0.5 + COALESCE((
                     SELECT COUNT(DISTINCT ep.id)
                       FROM explore_pool ep, json_each(ep.tags_json) je
                      WHERE ep.action IN ('skipped', 'passed') AND je.value = tag_dict.tag
                   ), 0)
            """
        )
    )
    conn.commit()


def downgrade() -> None:
    with op.batch_alter_table('tag_dict') as batch_op:
        batch_op.drop_column('alpha')
        batch_op.drop_column('beta')

    with op.batch_alter_table('explore_pool') as batch_op:
        batch_op.add_column(sa.Column('pre_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('embedding', sa.LargeBinary(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_explore_pool_pre_score ON explore_pool (pre_score)"
        )
    )
