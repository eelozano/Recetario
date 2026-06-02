"""Nutrition use cases: manual ingredient→USDA linking and macro calculation.

These orchestrate the recipe repository, the FDC cache, and the MacroCalculator
domain service. No HTTP, no ORM — only ports and domain objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from recetario.application.dto.nutrition_dto import FoodSummary
from recetario.application.ports import NutritionRepository, RecipeRepository
from recetario.application.use_cases.recipes import RecipeNotFoundError
from recetario.domain.entities import Recipe
from recetario.domain.services.macro_calculator import MacroCalculator, RecipeMacroBreakdown


class FoodNotCachedError(Exception):
    def __init__(self, fdc_id: int) -> None:
        super().__init__(f"USDA food {fdc_id} is not in the local cache; seed it first")
        self.fdc_id = fdc_id


class IngredientLineNotFoundError(Exception):
    def __init__(self, recipe_id: int, position: int) -> None:
        super().__init__(f"Recipe {recipe_id} has no ingredient at position {position}")
        self.recipe_id = recipe_id
        self.position = position


@dataclass
class LinkIngredientInput:
    recipe_id: int
    position: int
    fdc_id: int
    gram_weight: Decimal


class LinkRecipeIngredientToUsda:
    """Manually resolve one recipe line to a cached FDC food + gram weight."""

    def __init__(self, recipes: RecipeRepository, nutrition: NutritionRepository) -> None:
        self._recipes = recipes
        self._nutrition = nutrition

    def __call__(self, data: LinkIngredientInput) -> Recipe:
        recipe = self._recipes.get(data.recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(data.recipe_id)
        if self._nutrition.get_food(data.fdc_id) is None:
            raise FoodNotCachedError(data.fdc_id)

        line = next(
            (item for item in recipe.ingredients if item.position == data.position), None
        )
        if line is None:
            raise IngredientLineNotFoundError(data.recipe_id, data.position)

        line.usda_fdc_id = data.fdc_id
        line.gram_weight = data.gram_weight

        updated = self._recipes.update(recipe)
        if updated is None:
            raise RecipeNotFoundError(data.recipe_id)
        return updated


class CalculateRecipeMacros:
    def __init__(
        self,
        recipes: RecipeRepository,
        nutrition: NutritionRepository,
        calculator: MacroCalculator,
    ) -> None:
        self._recipes = recipes
        self._nutrition = nutrition
        self._calculator = calculator

    def __call__(self, recipe_id: int) -> RecipeMacroBreakdown:
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(recipe_id)

        fdc_ids = {
            fid
            for line in recipe.ingredients
            if (fid := line.usda_fdc_id or line.ingredient.usda_fdc_id) is not None
        }
        index = self._nutrition.nutrient_amounts(list(fdc_ids))
        return self._calculator.calculate(recipe, index)


class SearchCachedFoods:
    def __init__(self, nutrition: NutritionRepository) -> None:
        self._nutrition = nutrition

    def __call__(self, query: str, *, limit: int = 20) -> list[FoodSummary]:
        return self._nutrition.search_cached(query, limit=limit)
