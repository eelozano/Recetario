"""phase3 ingestion jobs

Revision ID: b7e2c9a1f4d3
Revises: 4a42f0e9e0ee
Create Date: 2026-06-02 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2c9a1f4d3'
down_revision: Union[str, None] = '4a42f0e9e0ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingestion_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('input_url', sa.String(length=2048), nullable=False),
        sa.Column('input_type', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('result_recipe_id', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ['result_recipe_id'], ['recipes.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('ingestion_jobs')
