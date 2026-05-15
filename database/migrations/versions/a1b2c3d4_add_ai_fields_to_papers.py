"""add_ai_fields_to_papers

Revision ID: a1b2c3d4_add_ai_fields
Revises: d1f07bec4a68
Create Date: 2026-05-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4_add_ai_fields'
down_revision: Union[str, Sequence[str], None] = 'a3f2b1c4reset'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tags', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('ai_summary', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('ai_analyzed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('ai_analyzed_at')
        batch_op.drop_column('ai_summary')
        batch_op.drop_column('tags')
