"""MealPlanAggregator — per-day and whole-range macro totals for a meal plan.

Pure domain service: it is fed each planned meal's *per-serving* macro profile
(computed upstream by MacroCalculator) plus how many servings are planned, and it
scales + groups them by date. This is what powers the calendar's "calories this
day / this week" rollups, reusing the same macro math as the recipe view.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal

from recetario.domain.entities.meal import MealType
from recetario.domain.value_objects.macro import MacroProfile


@dataclass(frozen=True)
class PlannedMeal:
    """A meal event reduced to what the aggregator needs: when, how much, and the
    recipe's per-serving macro profile."""

    date: Date
    meal_type: MealType
    servings_planned: Decimal
    per_serving: MacroProfile


@dataclass(frozen=True)
class DayMacros:
    date: Date
    totals: MacroProfile


@dataclass(frozen=True)
class WeekMacroSummary:
    """Per-day totals (sorted by date) plus the grand total across the range."""

    days: list[DayMacros] = field(default_factory=list)
    totals: MacroProfile = field(default_factory=lambda: MacroProfile({}))


class MealPlanAggregator:
    def aggregate(self, meals: Sequence[PlannedMeal]) -> WeekMacroSummary:
        by_day: dict[Date, MacroProfile] = {}
        for meal in meals:
            scaled = meal.per_serving.scale(meal.servings_planned)
            by_day[meal.date] = by_day.get(meal.date, MacroProfile({})) + scaled

        days = [DayMacros(date=d, totals=by_day[d]) for d in sorted(by_day)]

        grand = MacroProfile({})
        for day in days:
            grand = grand + day.totals

        return WeekMacroSummary(days=days, totals=grand)
