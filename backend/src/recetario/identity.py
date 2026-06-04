"""Single-user identity seam.

Today Recetario is a single-user desktop app: every owner-scoped row belongs to
one implicit owner. Rather than leave `owner_id` unused (and have to retrofit
scoping for the eventual multi-user web product), we stamp and filter rows by a
constant owner now.

The migration to multi-user is then **additive**, not a rewrite: the owner-scoped
repositories already take an `owner_id`, and the API resolves it in exactly one
place (`get_owner_id` in `api/deps.py`). Swap that resolver to read the
authenticated principal and the whole stack becomes multi-tenant — no changes to
domain, use cases, or repository internals.
"""

from __future__ import annotations

# The owner every row belongs to until real authentication exists. The `owner_id`
# columns are nullable in the schema; a backfill migration stamps legacy NULL rows
# to this value so they stay visible once scoping turns on.
DEFAULT_OWNER_ID = 1
