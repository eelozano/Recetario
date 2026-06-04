"""Meal-calendar use cases: schedule recipes into slots and roll up week macros.

These orchestrate the MealEventRepository, RecipeRepository, the FDC cache, and
the MacroCalculator / MealPlanAggregator domain services. No HTTP, no ORM.
"""

from __future__ import annotations

from datetime import date as Date

from recetario.application.dto import MealEventInput
from recetario.application.ports import (
    MealEventRepository,
    NutritionRepository,
    RecipeRepository,
)
from recetario.application.use_cases.recipes import RecipeNotFoundError
from recetario.domain.entities import MealEvent
from recetario.domain.services.macro_calculator import MacroCalculator
from recetario.domain.services.meal_planner import (
    MealPlanAggregator,
    PlannedMeal,
    WeekMacroSummary,
)
from recetario.domain.value_objects.macro import MacroProfile


class MealEventNotFoundError(Exception):
    def __init__(self, event_id: int) -> None:
        super().__init__(f"Meal event {event_id} not found")
        self.event_id = event_id


def _to_domain(data: MealEventInput) -> MealEvent:
    return MealEvent(
        date=data.date,
        meal_type=data.meal_type,
        recipe_id=data.recipe_id,
        servings_planned=data.servings_planned,
        notes=data.notes,
    )


class ScheduleMeal:
    """Place a recipe into a meal slot. Rejects unknown recipes up front."""

    def __init__(self, meals: MealEventRepository, recipes: RecipeRepository) -> None:
        self._meals = meals
        self._recipes = recipes

    def __call__(self, data: MealEventInput) -> MealEvent:
        if self._recipes.get(data.recipe_id) is None:
            raise RecipeNotFoundError(data.recipe_id)
        return self._meals.add(_to_domain(data))


class GetMealEvent:
    def __init__(self, meals: MealEventRepository) -> None:
        self._meals = meals

    def __call__(self, event_id: int) -> MealEvent:
        event = self._meals.get(event_id)
        if event is None:
            raise MealEventNotFoundError(event_id)
        return event


class ListWeek:
    def __init__(self, meals: MealEventRepository) -> None:
        self._meals = meals

    def __call__(self, start: Date, end: Date) -> list[MealEvent]:
        return self._meals.list_range(start, end)


class UpdateMealEvent:
    def __init__(self, meals: MealEventRepository, recipes: RecipeRepository) -> None:
        self._meals = meals
        self._recipes = recipes

    def __call__(self, event_id: int, data: MealEventInput) -> MealEvent:
        if self._recipes.get(data.recipe_id) is None:
            raise RecipeNotFoundError(data.recipe_id)
        entity = _to_domain(data)
        entity.id = event_id
        updated = self._meals.update(entity)
        if updated is None:
            raise MealEventNotFoundError(event_id)
        return updated


class DeleteMealEvent:
    def __init__(self, meals: MealEventRepository) -> None:
        self._meals = meals

    def __call__(self, event_id: int) -> None:
        if not self._meals.delete(event_id):
            raise MealEventNotFoundError(event_id)


class CalculateWeekMacros:
    """Aggregate per-day and whole-range macro totals for the scheduled meals.

    Each recipe's per-serving macro profile is computed once (via MacroCalculator)
    and scaled by each event's planned servings, then grouped by date.
    """

    def __init__(
        self,
        meals: MealEventRepository,
        recipes: RecipeRepository,
        nutrition: NutritionRepository,
        calculator: MacroCalculator,
        aggregator: MealPlanAggregator,
    ) -> None:
        self._meals = meals
        self._recipes = recipes
        self._nutrition = nutrition
        self._calculator = calculator
        self._aggregator = aggregator

    def _per_serving(self, recipe_id: int) -> MacroProfile:
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            return MacroProfile({})
        fdc_ids = {
            fid
            for line in recipe.ingredients
            if (fid := line.usda_fdc_id or line.ingredient.usda_fdc_id) is not None
        }
        index = self._nutrition.nutrient_amounts(list(fdc_ids))
        breakdown = self._calculator.calculate(recipe, index)
        # Fall back to the recipe total when no yield is recorded (treat as 1 serving).
        return breakdown.per_serving if breakdown.per_serving is not None else breakdown.totals

    def __call__(self, start: Date, end: Date) -> WeekMacroSummary:
        events = self._meals.list_range(start, end)
        cache: dict[int, MacroProfile] = {}
        planned: list[PlannedMeal] = []
        for event in events:
            if event.recipe_id not in cache:
                cache[event.recipe_id] = self._per_serving(event.recipe_id)
            planned.append(
                PlannedMeal(
                    date=event.date,
                    meal_type=event.meal_type,
                    servings_planned=event.servings_planned,
                    per_serving=cache[event.recipe_id],
                )
            )
        return self._aggregator.aggregate(planned)
