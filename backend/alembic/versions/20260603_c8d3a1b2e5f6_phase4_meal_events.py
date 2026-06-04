"""phase4 meal events

Revision ID: c8d3a1b2e5f6
Revises: b7e2c9a1f4d3
Create Date: 2026-06-03 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d3a1b2e5f6'
down_revision: Union[str, None] = 'b7e2c9a1f4d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meal_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('meal_type', sa.String(length=16), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('servings_planned', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_meal_events_date', 'meal_events', ['date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_meal_events_date', table_name='meal_events')
    op.drop_table('meal_events')
