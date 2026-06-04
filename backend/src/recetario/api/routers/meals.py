"""Meal-calendar endpoints. Thin: validate, call a use case, map to a schema.

A "week" is a date range, so the list endpoint takes `start`/`end` and returns
the scheduled events plus per-day and whole-range macro rollups in one payload.
"""

from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from recetario.api import deps
from recetario.api.schemas import MealEventCreate, MealEventOut, WeekMacrosOut, WeekPlanOut
from recetario.application.use_cases.meal import (
    CalculateWeekMacros,
    DeleteMealEvent,
    GetMealEvent,
    ListWeek,
    MealEventNotFoundError,
    ScheduleMeal,
    UpdateMealEvent,
)
from recetario.application.use_cases.recipes import RecipeNotFoundError

router = APIRouter(prefix="/meals", tags=["meals"])


@router.post("", response_model=MealEventOut, status_code=status.HTTP_201_CREATED)
def schedule_meal(payload: MealEventCreate, uc: ScheduleMeal = Depends(deps.schedule_meal_uc)):
    try:
        return MealEventOut.from_domain(uc(payload.to_input()))
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


@router.get("", response_model=WeekPlanOut)
def week_plan(
    start: Date = Query(...),
    end: Date = Query(...),
    list_uc: ListWeek = Depends(deps.list_week_uc),
    macros_uc: CalculateWeekMacros = Depends(deps.week_macros_uc),
):
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`end` must be on or after `start`",
        )
    events = list_uc(start, end)
    summary = macros_uc(start, end)
    return WeekPlanOut(
        start=start,
        end=end,
        events=[MealEventOut.from_domain(e) for e in events],
        macros=WeekMacrosOut.from_domain(summary),
    )


@router.get("/{event_id}", response_model=MealEventOut)
def get_meal(event_id: int, uc: GetMealEvent = Depends(deps.get_meal_uc)):
    try:
        return MealEventOut.from_domain(uc(event_id))
    except MealEventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal event not found")


@router.put("/{event_id}", response_model=MealEventOut)
def update_meal(
    event_id: int,
    payload: MealEventCreate,
    uc: UpdateMealEvent = Depends(deps.update_meal_uc),
):
    try:
        return MealEventOut.from_domain(uc(event_id, payload.to_input()))
    except MealEventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal event not found")
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(event_id: int, uc: DeleteMealEvent = Depends(deps.delete_meal_uc)):
    try:
        uc(event_id)
    except MealEventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal event not found")
