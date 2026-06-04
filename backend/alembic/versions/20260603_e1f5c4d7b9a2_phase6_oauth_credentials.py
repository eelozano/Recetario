"""phase6 oauth credentials + export tasklist id

Revision ID: e1f5c4d7b9a2
Revises: d9e4b3c6a7f8
Create Date: 2026-06-03 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f5c4d7b9a2'
down_revision: Union[str, None] = 'd9e4b3c6a7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oauth_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('encrypted_data', sa.Text(), nullable=False),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider'),
    )
    op.add_column(
        'shopping_lists',
        sa.Column('external_tasklist_id', sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('shopping_lists', 'external_tasklist_id')
    op.drop_table('oauth_credentials')
