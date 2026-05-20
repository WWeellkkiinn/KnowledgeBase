"""add tag pool tables

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-20 00:00:00.000000

"""
from __future__ import annotations

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


tag_dict_table = sa.table(
    'tag_dict',
    sa.column('tag', sa.String(32)),
    sa.column('source', sa.String(16)),
)


def upgrade() -> None:
    op.create_table(
        'tag_dict',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tag', sa.String(32), nullable=False, unique=True),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
    )
    op.create_index('ix_tag_dict_tag', 'tag_dict', ['tag'], unique=True)
    op.create_index('ix_tag_dict_source', 'tag_dict', ['source'])

    op.create_table(
        'tag_proposals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tag', sa.String(32), nullable=False),
        sa.Column(
            'explore_pool_id',
            sa.Integer(),
            sa.ForeignKey('explore_pool.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'proposed_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
    )
    op.create_index('ix_tag_proposals_tag', 'tag_proposals', ['tag'])
    op.create_index('ix_tag_proposals_explore_pool_id', 'tag_proposals', ['explore_pool_id'])

    try:
        tag_dump_path = Path(r'C:\dev\KnowledgeBase\.tag_dump.txt')
        merge_plan_path = Path(r'C:\dev\KnowledgeBase\.tag_merge_plan.json')
        if not tag_dump_path.exists() or not merge_plan_path.exists():
            print('WARNING: tag seed files missing; skipping tag_dict seed')
            return

        all_tags = {
            line.strip()
            for line in tag_dump_path.read_text(encoding='utf-8').splitlines()
            if line.strip()
        }
        merge_plan = json.loads(merge_plan_path.read_text(encoding='utf-8'))
        aliases = set(merge_plan.get('mapping_flat', {}).keys())
        canonicals = all_tags - aliases
        op.bulk_insert(
            tag_dict_table,
            [{'tag': tag, 'source': 'seed'} for tag in sorted(canonicals)],
        )
    except Exception as exc:
        print(f'WARNING: failed to seed tag_dict: {exc}')


def downgrade() -> None:
    op.drop_table('tag_proposals')
    op.drop_table('tag_dict')
