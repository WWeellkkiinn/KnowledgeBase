"""add_scoring_to_sub_results

新增 subscription_results.llm_score / llm_reason / scored_at，供 LLM 相关性评分写入。

Revision ID: e2f3a4b5c6d7
Revises: d1a2b3c4e5f6
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1a2b3c4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("subscription_results") as batch_op:
        batch_op.add_column(sa.Column("llm_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("llm_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("scored_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("subscription_results") as batch_op:
        batch_op.drop_column("scored_at")
        batch_op.drop_column("llm_reason")
        batch_op.drop_column("llm_score")
