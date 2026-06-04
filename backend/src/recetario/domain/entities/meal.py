"""Meal-calendar domain entities — pure, framework-free.

A `MealEvent` schedules one recipe into a meal slot on a given date. A "week" is
simply the set of events whose date falls in a range — no separate week entity
(see DESIGN.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from enum import Enum


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass
class MealEvent:
    """A scheduled recipe in a meal slot.

    `servings_planned` is how many servings of the recipe are planned for this
    slot; macro aggregation scales the recipe's per-serving profile by it.
    `recipe_title` is a read-time convenience populated by the repository for the
    calendar view; it is not persisted on this row.
    """

    date: Date
    meal_type: MealType
    recipe_id: int
    servings_planned: Decimal = Decimal(1)
    notes: str | None = None
    id: int | None = None
    recipe_title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
