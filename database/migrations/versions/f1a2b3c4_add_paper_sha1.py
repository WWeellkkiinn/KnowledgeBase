"""add_paper_sha1

Revision ID: f1a2b3c4_paper_sha1
Revises: a1b2c3d4_add_ai_fields
Create Date: 2026-05-15 00:00:00.000000

为 papers 表新增 sha1 列，用于上传去重（与 DOI 共同构成去重双轨）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4_paper_sha1'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4_add_ai_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sha1', sa.String(40), nullable=True))
    # unique + index 单独建（partial 在 SQLite 上 batch 不便处理）
    op.create_index('ux_papers_sha1', 'papers', ['sha1'], unique=True)


def downgrade() -> None:
    op.drop_index('ux_papers_sha1', table_name='papers')
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('sha1')
