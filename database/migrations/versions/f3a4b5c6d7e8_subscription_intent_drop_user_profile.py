"""subscription_intent_drop_user_profile

add description + generated_queries to subscriptions + drop user_profile

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("generated_queries", sa.JSON(), nullable=True))

    op.drop_table("user_profile")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_hint", sa.Text(), nullable=True),
        sa.CheckConstraint("id = 1", name="user_profile_single_row"),
    )

    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.drop_column("generated_queries")
        batch_op.drop_column("description")
