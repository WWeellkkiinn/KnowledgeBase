"""simplify user_profile to user_hint only + drop recommendations table

Revision ID: d1a2b3c4e5f6
Revises: c8f5e3a72d44
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c8f5e3a72d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('recommendations')
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_column('profile_json')
        batch_op.drop_column('generated_at')
        batch_op.drop_column('source_paper_count')
        batch_op.drop_column('model')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.add_column(sa.Column('model', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('source_paper_count', sa.Integer(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01'")))
        batch_op.add_column(sa.Column('profile_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

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
