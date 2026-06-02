"""Repository ports — abstract persistence boundaries.

Use cases depend on these Protocols, never on SQLAlchemy. Infrastructure provides
the concrete adapters. This is what keeps the core swappable (SQLite → Postgres,
or an entirely different store) without touching business logic.
"""

from __future__ import annotations

from typing import Protocol

from recetario.domain.entities import Recipe, Tag


class RecipeRepository(Protocol):
    def add(self, recipe: Recipe) -> Recipe: ...

    def get(self, recipe_id: int) -> Recipe | None: ...

    def list(self, *, tag: str | None = None, search: str | None = None) -> list[Recipe]: ...

    def update(self, recipe: Recipe) -> Recipe | None: ...

    def delete(self, recipe_id: int) -> bool: ...


class TagRepository(Protocol):
    def list(self) -> list[Tag]: ...
