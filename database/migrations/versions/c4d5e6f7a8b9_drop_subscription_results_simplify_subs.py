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


def upgrade():
    op.drop_table('subscription_results')

    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_column('type')
        batch_op.drop_column('target_json')
        batch_op.drop_column('cron_expr')
        batch_op.drop_column('last_run_at')
        batch_op.drop_column('next_run_at')
        batch_op.drop_column('last_notified_at')


def downgrade():
    pass
