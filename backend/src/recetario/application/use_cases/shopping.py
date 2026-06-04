"""Shopping-list use cases: generate a week's grocery list and check items off.

GenerateWeeklyShoppingList walks the meal events in a date range, scales each
recipe's ingredient quantities by the planned servings, and hands them to the
ShoppingAggregator to dedupe + sum. The result is persisted so check-off state
(and later Google Tasks export) survives.
"""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal

from recetario.application.ports import (
    MealEventRepository,
    RecipeRepository,
    ShoppingListRepository,
)
from recetario.domain.entities import ShoppingList, ShoppingListItem
from recetario.domain.services.shopping_aggregator import ShoppingAggregator, ShoppingDemand


class ShoppingListNotFoundError(Exception):
    def __init__(self, list_id: int) -> None:
        super().__init__(f"Shopping list {list_id} not found")
        self.list_id = list_id


class ShoppingItemNotFoundError(Exception):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"Shopping list item {item_id} not found")
        self.item_id = item_id


class GenerateWeeklyShoppingList:
    def __init__(
        self,
        lists: ShoppingListRepository,
        meals: MealEventRepository,
        recipes: RecipeRepository,
        aggregator: ShoppingAggregator,
    ) -> None:
        self._lists = lists
        self._meals = meals
        self._recipes = recipes
        self._aggregator = aggregator

    def __call__(
        self, week_start: Date, week_end: Date, *, name: str | None = None
    ) -> ShoppingList:
        events = self._meals.list_range(week_start, week_end)

        recipe_cache: dict[int, object] = {}
        demands: list[ShoppingDemand] = []
        for event in events:
            recipe = recipe_cache.get(event.recipe_id)
            if recipe is None:
                recipe = self._recipes.get(event.recipe_id)
                if recipe is None:
                    continue
                recipe_cache[event.recipe_id] = recipe

            # Scale each line by planned servings relative to the recipe yield
            # (no yield → treat the recipe as a single serving).
            servings = recipe.servings or 1
            factor = event.servings_planned / Decimal(servings)
            for line in recipe.ingredients:
                quantity = line.quantity * factor if line.quantity is not None else None
                demands.append(
                    ShoppingDemand(
                        ingredient_name=line.ingredient.name,
                        normalized_name=line.ingredient.normalized_name,
                        quantity=quantity,
                        unit=line.unit,
                        ingredient_id=line.ingredient.id,
                        source_event_id=event.id,
                    )
                )

        items = self._aggregator.aggregate(demands)
        shopping_list = ShoppingList(
            name=name or f"Groceries — week of {week_start.isoformat()}",
            week_start=week_start,
            week_end=week_end,
            items=[
                ShoppingListItem(
                    ingredient_id=item.ingredient_id,
                    ingredient_name=item.ingredient_name,
                    unit=item.unit,
                    total_quantity=item.total_quantity,
                    source_event_ids=item.source_event_ids,
                )
                for item in items
            ],
        )
        return self._lists.add(shopping_list)


class GetShoppingList:
    def __init__(self, lists: ShoppingListRepository) -> None:
        self._lists = lists

    def __call__(self, list_id: int) -> ShoppingList:
        shopping_list = self._lists.get(list_id)
        if shopping_list is None:
            raise ShoppingListNotFoundError(list_id)
        return shopping_list


class ListShoppingLists:
    def __init__(self, lists: ShoppingListRepository) -> None:
        self._lists = lists

    def __call__(self) -> list[ShoppingList]:
        return self._lists.list()


class DeleteShoppingList:
    def __init__(self, lists: ShoppingListRepository) -> None:
        self._lists = lists

    def __call__(self, list_id: int) -> None:
        if not self._lists.delete(list_id):
            raise ShoppingListNotFoundError(list_id)


class ToggleShoppingItem:
    def __init__(self, lists: ShoppingListRepository) -> None:
        self._lists = lists

    def __call__(self, item_id: int, checked: bool) -> ShoppingListItem:
        item = self._lists.set_item_checked(item_id, checked)
        if item is None:
            raise ShoppingItemNotFoundError(item_id)
        return item
