"""reset stub is_core

Revision ID: a3f2b1c4reset
Revises: c40c7aeae9fe
Create Date: 2026-05-14 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a3f2b1c4reset'
down_revision: Union[str, Sequence[str], None] = 'c40c7aeae9fe'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(
        "UPDATE papers SET is_core = 0 WHERE source IN ('ref', 'forward')"
    )

def downgrade() -> None:
    # 此迁移不可逆：已被重置为 stub 的论文无法自动还原 is_core=True。
    # 如需回滚，请手动在数据库中根据业务逻辑重新标记核心论文。
    pass
