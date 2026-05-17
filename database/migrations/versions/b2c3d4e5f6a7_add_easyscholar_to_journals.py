"""add easyscholar columns to journals

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('journals') as batch_op:
        batch_op.add_column(sa.Column('easyscholar_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('easyscholar_fetched_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('journals') as batch_op:
        batch_op.drop_column('easyscholar_fetched_at')
        batch_op.drop_column('easyscholar_json')
