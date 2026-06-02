"""Nutrition ports — the boundaries for USDA FoodData Central access.

`NutritionProvider` is the *live* source (the FDC HTTP API); `NutritionRepository`
is the *local cache* the seeder fills and the macro math reads from. Keeping them
separate lets the app run fully offline against the cache while the provider is
only needed when seeding or resolving new ingredients.
"""

from __future__ import annotations

from typing import Protocol

from recetario.application.dto.nutrition_dto import FoodDetail, FoodSummary
from recetario.domain.value_objects.macro import NutrientAmount


class NutritionProvider(Protocol):
    """Live USDA FDC access (the network adapter)."""

    def search(self, query: str, *, page_size: int = 5) -> list[FoodSummary]: ...

    def get_food(self, fdc_id: int) -> FoodDetail | None: ...


class NutritionRepository(Protocol):
    """The local FDC cache: usda_foods / usda_food_nutrients / usda_food_portions."""

    def upsert_food(self, detail: FoodDetail) -> None: ...

    def get_food(self, fdc_id: int) -> FoodDetail | None: ...

    def search_cached(self, query: str, *, limit: int = 20) -> list[FoodSummary]: ...

    def nutrient_amounts(self, fdc_ids: list[int]) -> dict[int, list[NutrientAmount]]:
        """Per-100g nutrient amounts keyed by fdc_id, for the MacroCalculator."""
        ...
