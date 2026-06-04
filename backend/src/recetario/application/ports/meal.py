"""Meal-calendar repository port — the persistence boundary for meal events.

Use cases depend on this Protocol, never on SQLAlchemy.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from recetario.domain.entities import MealEvent


class MealEventRepository(Protocol):
    def add(self, event: MealEvent) -> MealEvent: ...

    def get(self, event_id: int) -> MealEvent | None: ...

    def list_range(self, start: Date, end: Date) -> list[MealEvent]: ...

    def update(self, event: MealEvent) -> MealEvent | None: ...

    def delete(self, event_id: int) -> bool: ...
