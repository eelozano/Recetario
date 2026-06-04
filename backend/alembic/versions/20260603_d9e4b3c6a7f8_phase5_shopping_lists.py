"""phase5 shopping lists

Revision ID: d9e4b3c6a7f8
Revises: c8d3a1b2e5f6
Create Date: 2026-06-03 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e4b3c6a7f8'
down_revision: Union[str, None] = 'c8d3a1b2e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        'shopping_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'shopping_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shopping_list_id', sa.Integer(), nullable=False),
        sa.Column('ingredient_id', sa.Integer(), nullable=True),
        sa.Column('ingredient_name', sa.String(length=255), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('total_quantity', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('checked', sa.Boolean(), nullable=False),
        sa.Column('external_task_id', sa.String(length=128), nullable=True),
        sa.Column('source_event_ids', sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ['shopping_list_id'], ['shopping_lists.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('shopping_list_items')
    op.drop_table('shopping_lists')
