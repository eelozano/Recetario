"""Pydantic models for the meal-calendar HTTP boundary."""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field

from recetario.application.dto import MealEventInput
from recetario.domain.entities import MealEvent, MealType
from recetario.domain.services.meal_planner import DayMacros, WeekMacroSummary


class MealEventCreate(BaseModel):
    date: Date
    meal_type: MealType
    recipe_id: int
    servings_planned: Decimal = Field(default=Decimal(1), gt=0)
    notes: str | None = None

    def to_input(self) -> MealEventInput:
        return MealEventInput(
            date=self.date,
            meal_type=self.meal_type,
            recipe_id=self.recipe_id,
            servings_planned=self.servings_planned,
            notes=self.notes,
        )


class MealEventOut(BaseModel):
    id: int
    date: Date
    meal_type: MealType
    recipe_id: int
    recipe_title: str | None
    servings_planned: Decimal
    notes: str | None

    @classmethod
    def from_domain(cls, event: MealEvent) -> "MealEventOut":
        return cls(
            id=event.id,
            date=event.date,
            meal_type=event.meal_type,
            recipe_id=event.recipe_id,
            recipe_title=event.recipe_title,
            servings_planned=event.servings_planned,
            notes=event.notes,
        )


class DayMacrosOut(BaseModel):
    date: Date
    totals: dict[str, Decimal]

    @classmethod
    def from_domain(cls, day: DayMacros) -> "DayMacrosOut":
        return cls(date=day.date, totals=dict(day.totals.amounts))


class WeekMacrosOut(BaseModel):
    days: list[DayMacrosOut]
    totals: dict[str, Decimal]

    @classmethod
    def from_domain(cls, summary: WeekMacroSummary) -> "WeekMacrosOut":
        return cls(
            days=[DayMacrosOut.from_domain(d) for d in summary.days],
            totals=dict(summary.totals.amounts),
        )


class WeekPlanOut(BaseModel):
    """Everything the calendar needs for a date range in one response:
    the scheduled events plus the per-day and whole-range macro rollups."""

    start: Date
    end: Date
    events: list[MealEventOut]
    macros: WeekMacrosOut
