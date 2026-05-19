"""explore_unique_and_attempts

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-05-19 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def _has_column(table: str, col: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _has_index(name: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        f"SELECT name FROM sqlite_master WHERE type='index' AND name='{name}'"
    ).fetchall()
    return bool(rows)


def upgrade() -> None:
    # 1. ExplorePool: add external_id
    if not _has_column('explore_pool', 'external_id'):
        op.add_column('explore_pool', sa.Column('external_id', sa.String(255), nullable=True))
    if not _has_index('ix_explore_pool_external_id'):
        op.create_index('ix_explore_pool_external_id', 'explore_pool', ['external_id'])

    # 2. Backfill external_id from raw_metadata_json (idempotent — only fills NULL rows)
    op.execute(
        "UPDATE explore_pool SET external_id = json_extract(raw_metadata_json, '$.external_id') "
        "WHERE external_id IS NULL"
    )

    # 3. ExplorePool: add score_attempts
    if not _has_column('explore_pool', 'score_attempts'):
        op.add_column('explore_pool', sa.Column(
            'score_attempts', sa.Integer(), nullable=False, server_default='0'
        ))

    # 4. SubscriptionResult: add score_attempts
    if not _has_column('subscription_results', 'score_attempts'):
        op.add_column('subscription_results', sa.Column(
            'score_attempts', sa.Integer(), nullable=False, server_default='0'
        ))

    # 5. Subscription: add last_filled_at
    if not _has_column('subscriptions', 'last_filled_at'):
        op.add_column('subscriptions', sa.Column('last_filled_at', sa.DateTime(), nullable=True))

    # 6. Dedup existing rows before adding unique constraint
    #    Keep the row with the highest id (most recent insertion) per (sub_id, external_id) group.
    op.execute("""
        DELETE FROM explore_pool
        WHERE external_id IS NOT NULL
          AND id NOT IN (
            SELECT MAX(id) FROM explore_pool
            WHERE external_id IS NOT NULL
            GROUP BY subscription_id, external_id
          )
    """)

    # 7. ExplorePool: add unique constraint on (subscription_id, external_id)
    if not _has_index('uq_explore_sub_external'):
        op.create_index(
            'uq_explore_sub_external',
            'explore_pool',
            ['subscription_id', 'external_id'],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index('uq_explore_sub_external', table_name='explore_pool')
    op.drop_column('subscriptions', 'last_filled_at')
    op.drop_column('subscription_results', 'score_attempts')
    op.drop_column('explore_pool', 'score_attempts')
    op.drop_index('ix_explore_pool_external_id', table_name='explore_pool')
    op.drop_column('explore_pool', 'external_id')
