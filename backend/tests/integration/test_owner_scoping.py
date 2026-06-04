"""Owner-scoping seam (Phase 7).

Proves the repositories isolate rows by ``owner_id``: a repo bound to one owner
cannot see, fetch, mutate, or delete another owner's rows. This is what makes the
eventual multi-user migration additive — the scoping already holds at the
persistence boundary; only the owner *resolution* (api/deps.get_owner_id) needs to
change.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from recetario.domain.entities import (
    MealEvent,
    MealType,
    Recipe,
    ShoppingList,
    ShoppingListItem,
)
from recetario.infrastructure.db.repositories import (
    SqlAlchemyMealEventRepository,
    SqlAlchemyRecipeRepository,
    SqlAlchemyShoppingListRepository,
)

OWNER_A = 1
OWNER_B = 2


@pytest.fixture
def session(db_engine: Engine) -> Session:
    # `db_engine` (conftest) is SQLite by default, or the configured Postgres
    # when RECETARIO_TEST_DATABASE_URL is set — so this scoping test validates on
    # both backends.
    with Session(db_engine, future=True) as s:
        yield s


def _recipe(title: str) -> Recipe:
    return Recipe(title=title)


def test_recipe_repo_isolates_by_owner(session: Session) -> None:
    repo_a = SqlAlchemyRecipeRepository(session, owner_id=OWNER_A)
    repo_b = SqlAlchemyRecipeRepository(session, owner_id=OWNER_B)

    mine = repo_a.add(_recipe("A's soup"))
    repo_b.add(_recipe("B's stew"))

    # Each owner sees only their own list.
    assert [r.title for r in repo_a.list()] == ["A's soup"]
    assert [r.title for r in repo_b.list()] == ["B's stew"]

    # B cannot fetch, update, or delete A's recipe.
    assert repo_b.get(mine.id) is None
    assert repo_b.update(Recipe(id=mine.id, title="hijacked")) is None
    assert repo_b.delete(mine.id) is False
    # A still owns an untouched recipe.
    assert repo_a.get(mine.id).title == "A's soup"


def test_meal_repo_isolates_by_owner(session: Session) -> None:
    # A recipe to reference (FK); owner of the recipe is irrelevant to the meal.
    recipe = SqlAlchemyRecipeRepository(session, owner_id=OWNER_A).add(_recipe("Base"))
    repo_a = SqlAlchemyMealEventRepository(session, owner_id=OWNER_A)
    repo_b = SqlAlchemyMealEventRepository(session, owner_id=OWNER_B)

    day = dt.date(2026, 6, 4)
    mine = repo_a.add(
        MealEvent(date=day, meal_type=MealType.DINNER, recipe_id=recipe.id)
    )
    repo_b.add(MealEvent(date=day, meal_type=MealType.LUNCH, recipe_id=recipe.id))

    week = (dt.date(2026, 6, 1), dt.date(2026, 6, 7))
    assert [m.meal_type for m in repo_a.list_range(*week)] == [MealType.DINNER]
    assert [m.meal_type for m in repo_b.list_range(*week)] == [MealType.LUNCH]

    assert repo_b.get(mine.id) is None
    assert repo_b.delete(mine.id) is False
    assert repo_a.get(mine.id) is not None


def _shopping(name: str) -> ShoppingList:
    return ShoppingList(
        name=name,
        week_start=dt.date(2026, 6, 1),
        week_end=dt.date(2026, 6, 7),
        items=[ShoppingListItem(ingredient_name="Onion", unit="pc", total_quantity=Decimal(2))],
    )


def test_shopping_repo_isolates_by_owner(session: Session) -> None:
    repo_a = SqlAlchemyShoppingListRepository(session, owner_id=OWNER_A)
    repo_b = SqlAlchemyShoppingListRepository(session, owner_id=OWNER_B)

    mine = repo_a.add(_shopping("A's groceries"))
    repo_b.add(_shopping("B's groceries"))

    assert [sl.name for sl in repo_a.list()] == ["A's groceries"]
    assert [sl.name for sl in repo_b.list()] == ["B's groceries"]

    assert repo_b.get(mine.id) is None
    assert repo_b.delete(mine.id) is False
    # B cannot toggle an item belonging to A's list, even by item id.
    item_id = mine.items[0].id
    assert repo_b.set_item_checked(item_id, True) is None
    assert repo_a.set_item_checked(item_id, True) is not None
