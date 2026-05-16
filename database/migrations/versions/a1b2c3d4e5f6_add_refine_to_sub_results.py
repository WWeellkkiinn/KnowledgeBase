"""add_refine_to_sub_results

Add title_zh, tags_json, research_question, methodology, key_findings_json
to subscription_results table.

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("subscription_results") as batch_op:
        batch_op.add_column(sa.Column("title_zh", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("tags_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("research_question", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("methodology", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("key_findings_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("subscription_results") as batch_op:
        batch_op.drop_column("key_findings_json")
        batch_op.drop_column("methodology")
        batch_op.drop_column("research_question")
        batch_op.drop_column("tags_json")
        batch_op.drop_column("title_zh")
