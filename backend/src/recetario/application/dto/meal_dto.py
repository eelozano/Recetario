"""Framework-agnostic input DTO for scheduling/updating a meal event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

from recetario.domain.entities import MealType


@dataclass
class MealEventInput:
    date: Date
    meal_type: MealType
    recipe_id: int
    servings_planned: Decimal = Decimal(1)
    notes: str | None = None
