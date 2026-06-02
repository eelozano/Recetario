from decimal import Decimal

from recetario.domain.entities import Ingredient, Recipe, RecipeIngredient
from recetario.domain.services.macro_calculator import MacroCalculator
from recetario.domain.value_objects.macro import NutrientAmount


def _recipe() -> Recipe:
    return Recipe(
        title="Onion soup",
        servings=2,
        ingredients=[
            RecipeIngredient(
                id=1,
                position=0,
                ingredient=Ingredient(name="Onion", normalized_name="onion"),
                usda_fdc_id=170000,
                gram_weight=Decimal("200"),
            ),
            RecipeIngredient(
                id=2,
                position=1,
                ingredient=Ingredient(name="Salt", normalized_name="salt"),
            ),
        ],
    )


_INDEX = {
    170000: [
        NutrientAmount("calories", Decimal("40"), "kcal"),
        NutrientAmount("protein", Decimal("1.1"), "g"),
    ]
}


def test_per_line_contribution_scales_by_gram_weight():
    breakdown = MacroCalculator().calculate(_recipe(), _INDEX)

    onion = breakdown.lines[0]
    assert onion.resolved is True
    # 200 g => factor 2 over the per-100g basis.
    assert onion.profile.amounts["calories"] == Decimal("80")
    assert onion.profile.amounts["protein"] == Decimal("2.2")


def test_unresolved_line_contributes_nothing():
    breakdown = MacroCalculator().calculate(_recipe(), _INDEX)
    salt = breakdown.lines[1]
    assert salt.resolved is False
    assert salt.profile.amounts == {}
    assert breakdown.unresolved_count == 1


def test_totals_and_per_serving():
    breakdown = MacroCalculator().calculate(_recipe(), _INDEX)
    assert breakdown.totals.amounts["calories"] == Decimal("80")
    assert breakdown.per_serving is not None
    assert breakdown.per_serving.amounts["calories"] == Decimal("40")
    assert breakdown.per_serving.amounts["protein"] == Decimal("1.1")


def test_no_servings_means_no_per_serving():
    recipe = _recipe()
    recipe.servings = None
    breakdown = MacroCalculator().calculate(recipe, _INDEX)
    assert breakdown.per_serving is None
