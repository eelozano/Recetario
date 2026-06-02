from decimal import Decimal

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.use_cases.recipes import _normalize, _to_domain
from recetario.domain.entities import RecipeStatus


def test_normalize_collapses_whitespace_and_lowercases():
    assert _normalize("  Olive   OIL ") == "olive oil"


def test_to_domain_builds_entity_with_positions():
    data = RecipeInput(
        title="  Soup  ",
        status=RecipeStatus.FINALIZED,
        ingredients=[
            RecipeIngredientInput(name="Onion", quantity=Decimal("1"), unit="pc"),
            RecipeIngredientInput(name="Salt"),
        ],
        tags=["dinner", " ", "soup"],
    )
    recipe = _to_domain(data)

    assert recipe.title == "Soup"
    assert recipe.status is RecipeStatus.FINALIZED
    assert [i.position for i in recipe.ingredients] == [0, 1]
    assert recipe.ingredients[0].ingredient.normalized_name == "onion"
    assert [t.name for t in recipe.tags] == ["dinner", "soup"]  # blank tag dropped
