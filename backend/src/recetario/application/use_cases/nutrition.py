"""Nutrition use cases: manual ingredient→USDA linking and macro calculation.

These orchestrate the recipe repository, the FDC cache, and the MacroCalculator
domain service. No HTTP, no ORM — only ports and domain objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from recetario.application.dto.nutrition_dto import FoodSummary
from recetario.application.ports import NutritionProvider, NutritionRepository, RecipeRepository
from recetario.application.use_cases.recipes import RecipeNotFoundError
from recetario.domain.entities import Recipe
from recetario.domain.services.macro_calculator import MacroCalculator, RecipeMacroBreakdown


class FoodNotCachedError(Exception):
    """The chosen food isn't cached and there's no live provider to fetch it."""

    def __init__(self, fdc_id: int) -> None:
        super().__init__(f"USDA food {fdc_id} is not in the local cache; seed it first")
        self.fdc_id = fdc_id


class FoodNotFoundError(Exception):
    """The chosen food is neither cached nor known to the live FDC provider."""

    def __init__(self, fdc_id: int) -> None:
        super().__init__(f"USDA food {fdc_id} was not found in FoodData Central")
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
    """Manually resolve one recipe line to an FDC food + gram weight.

    If the chosen food isn't in the local cache, fetch it from the live FDC
    provider and cache it on the fly (so the macro math, which reads only from
    the cache, can use it). Absent a provider — no FDC key configured — linking
    is restricted to already-cached foods.
    """

    def __init__(
        self,
        recipes: RecipeRepository,
        nutrition: NutritionRepository,
        provider: NutritionProvider | None = None,
    ) -> None:
        self._recipes = recipes
        self._nutrition = nutrition
        self._provider = provider

    def __call__(self, data: LinkIngredientInput) -> Recipe:
        recipe = self._recipes.get(data.recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(data.recipe_id)
        if self._nutrition.get_food(data.fdc_id) is None:
            self._cache_food(data.fdc_id)

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

    def _cache_food(self, fdc_id: int) -> None:
        """Pull an uncached food from the live provider into the cache."""
        if self._provider is None:
            raise FoodNotCachedError(fdc_id)
        detail = self._provider.get_food(fdc_id)
        if detail is None:
            raise FoodNotFoundError(fdc_id)
        self._nutrition.upsert_food(detail)


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


class SearchFoods:
    """Find USDA foods to link a recipe line to.

    Prefers the live FDC provider when configured (so any food is findable, not
    just the seeded staples); falls back to the local cache when there's no key,
    keeping search usable fully offline.
    """

    def __init__(
        self, nutrition: NutritionRepository, provider: NutritionProvider | None = None
    ) -> None:
        self._nutrition = nutrition
        self._provider = provider

    def __call__(self, query: str, *, limit: int = 20) -> list[FoodSummary]:
        if self._provider is not None:
            return self._provider.search(query, page_size=limit)
        return self._nutrition.search_cached(query, limit=limit)
