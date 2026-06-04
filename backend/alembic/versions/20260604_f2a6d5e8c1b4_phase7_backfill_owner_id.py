"""phase7 backfill owner_id on owner-scoped tables

Phase 7 turns on owner scoping: the repositories now stamp every new row with the
default owner and filter all reads by it. Rows created before this seam carried a
NULL owner_id and would become invisible once filtering is active, so backfill the
legacy NULLs to the default owner. Idempotent and reversible.

Revision ID: f2a6d5e8c1b4
Revises: e1f5c4d7b9a2
Create Date: 2026-06-04 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a6d5e8c1b4'
down_revision: Union[str, None] = 'e1f5c4d7b9a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in lockstep with recetario.identity.DEFAULT_OWNER_ID. Hard-coded here so
# the migration stays a self-contained historical artifact (migrations must not
# import application code, which may drift).
_DEFAULT_OWNER_ID = 1

_OWNER_SCOPED_TABLES = ("recipes", "meal_events", "shopping_lists")


def upgrade() -> None:
    for table in _OWNER_SCOPED_TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET owner_id = :owner WHERE owner_id IS NULL"
            ).bindparams(owner=_DEFAULT_OWNER_ID)
        )


def downgrade() -> None:
    # Reverse the backfill: rows we stamped with the default owner go back to NULL.
    # (Indistinguishable from rows legitimately created under the default owner,
    # but downgrading past the scoping seam means owner identity no longer matters.)
    for table in _OWNER_SCOPED_TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET owner_id = NULL WHERE owner_id = :owner"
            ).bindparams(owner=_DEFAULT_OWNER_ID)
        )
