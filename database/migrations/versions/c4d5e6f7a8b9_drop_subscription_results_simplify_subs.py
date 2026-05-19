"""drop subscription_results and simplify subscriptions

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-19

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}'"
    ).fetchall()
    return bool(rows)


def _has_column(table: str, col: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def upgrade():
    if _has_table('subscription_results'):
        op.drop_table('subscription_results')

    # Drop stale indexes that reference columns being removed
    bind = op.get_bind()
    existing_indexes = {r[1] for r in bind.exec_driver_sql("PRAGMA index_list(subscriptions)").fetchall()}
    for idx in ('ix_subscriptions_active_next', 'ix_subscriptions_next_run_at'):
        if idx in existing_indexes:
            op.drop_index(idx, table_name='subscriptions')

    cols_to_drop = [c for c in ('type', 'target_json', 'cron_expr', 'last_run_at', 'next_run_at', 'last_notified_at')
                    if _has_column('subscriptions', c)]
    if cols_to_drop:
        with op.batch_alter_table('subscriptions', recreate='always') as batch_op:
            for col in cols_to_drop:
                batch_op.drop_column(col)


def downgrade():
    pass
