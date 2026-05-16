"""add_user_hint_to_profile

新增 user_profile.user_hint 可空字段，承载用户自定义研究兴趣画像 hint。

Revision ID: c8f5e3a72d44
Revises: b7e4f2a91c33
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f5e3a72d44'
down_revision: Union[str, Sequence[str], None] = 'b7e4f2a91c33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'user_profile',
        sa.Column('user_hint', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite 不支持 DROP COLUMN，走 batch_alter_table 重建。
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_column('user_hint')
