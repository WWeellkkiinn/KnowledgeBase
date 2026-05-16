"""add_llm_recommendations

Revision ID: b7e4f2a91c33
Revises: f1a2b3c4_paper_sha1
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4f2a91c33'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4_paper_sha1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # user_profile：单行画像表（CheckConstraint 锁 id=1）
    op.create_table(
        'user_profile',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_json', sa.JSON(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('source_paper_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('model', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='user_profile_single_row'),
    )

    # recommendations：LLM 评分流水
    op.create_table(
        'recommendations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('authors_json', sa.JSON(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('matched_theme', sa.Text(), nullable=True),
        sa.Column('relevance_score', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('saved_to_library', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_recommendations_external_id'),
            ['external_id'],
            unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recommendations_external_id'))
    op.drop_table('recommendations')
    op.drop_table('user_profile')
