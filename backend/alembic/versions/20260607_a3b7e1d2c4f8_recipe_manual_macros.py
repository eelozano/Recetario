"""recipe-level manual macros (#18)

Adds six nullable per-serving macro columns to `recipes` so users can record a
recipe's macros by hand instead of linking each ingredient to a USDA food.
Nullable with no default: an unset recipe simply has no manual macros and falls
back to the (now secondary) ingredient-level path.

Revision ID: a3b7e1d2c4f8
Revises: f2a6d5e8c1b4
Create Date: 2026-06-07 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b7e1d2c4f8'
down_revision: Union[str, None] = 'f2a6d5e8c1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "calories_per_serving",
    "protein_per_serving",
    "fat_per_serving",
    "carbs_per_serving",
    "fiber_per_serving",
    "sodium_per_serving",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("recipes", sa.Column(name, sa.Numeric(12, 3), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("recipes", name)
