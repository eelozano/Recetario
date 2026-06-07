"""MacroCalculator — the ingredient-level macro math.

Pure domain service: no DB, no network. It is fed a per-100g nutrient index
(keyed by FDC id) by the application layer and returns *both* the per-line
breakdown and the recipe totals. The per-line breakdown is the whole point — it
lets the UI answer "which ingredient is driving the fat / sodium?".

    contribution(nutrient) = (gram_weight / 100) * amount_per_100g
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from recetario.domain.entities import Recipe, RecipeIngredient
from recetario.domain.value_objects.macro import MacroProfile, NutrientAmount

_HUNDRED = Decimal(100)

# Maps the recipe's hand-entered per-serving fields to the canonical macro keys
# the rest of the app uses (matches the frontend's MACRO_ORDER / FDC nutrient
# names). Carbs/fiber/sodium use the long canonical key.
_MANUAL_FIELD_TO_KEY: dict[str, str] = {
    "calories_per_serving": "calories",
    "protein_per_serving": "protein",
    "fat_per_serving": "fat",
    "carbs_per_serving": "carbohydrate",
    "fiber_per_serving": "fiber",
    "sodium_per_serving": "sodium",
}


def manual_per_serving(recipe: Recipe) -> MacroProfile | None:
    """The recipe's hand-entered per-serving macros, or None if none are set.

    Only includes fields the user actually filled in, so an empty form leaves
    the ingredient-level path (USDA links) untouched.
    """
    amounts = {
        key: value
        for field_name, key in _MANUAL_FIELD_TO_KEY.items()
        if (value := getattr(recipe, field_name, None)) is not None
    }
    return MacroProfile(amounts) if amounts else None


@dataclass(frozen=True)
class LineMacro:
    """One recipe ingredient's macro contribution."""

    ingredient_name: str
    profile: MacroProfile
    resolved: bool
    recipe_ingredient_id: int | None = None
    fdc_id: int | None = None
    gram_weight: Decimal | None = None


@dataclass(frozen=True)
class RecipeMacroBreakdown:
    lines: list[LineMacro] = field(default_factory=list)
    totals: MacroProfile = field(default_factory=lambda: MacroProfile({}))
    per_serving: MacroProfile | None = None

    @property
    def unresolved_count(self) -> int:
        return sum(1 for line in self.lines if not line.resolved)


class MacroCalculator:
    def line_profile(
        self,
        line: RecipeIngredient,
        nutrient_index: Mapping[int, Sequence[NutrientAmount]],
    ) -> LineMacro:
        fdc_id = line.usda_fdc_id or line.ingredient.usda_fdc_id
        amounts = nutrient_index.get(fdc_id) if fdc_id is not None else None

        if fdc_id is None or line.gram_weight is None or not amounts:
            return LineMacro(
                ingredient_name=line.ingredient.name,
                profile=MacroProfile({}),
                resolved=False,
                recipe_ingredient_id=line.id,
                fdc_id=fdc_id,
                gram_weight=line.gram_weight,
            )

        factor = line.gram_weight / _HUNDRED
        profile = MacroProfile(
            {na.nutrient: (factor * na.amount) for na in amounts}
        )
        return LineMacro(
            ingredient_name=line.ingredient.name,
            profile=profile,
            resolved=True,
            recipe_ingredient_id=line.id,
            fdc_id=fdc_id,
            gram_weight=line.gram_weight,
        )

    def calculate(
        self,
        recipe: Recipe,
        nutrient_index: Mapping[int, Sequence[NutrientAmount]],
    ) -> RecipeMacroBreakdown:
        # Hand-entered per-serving macros win when present: they are the primary
        # workflow (#18). Totals scale up by the yield; no per-ingredient lines.
        manual = manual_per_serving(recipe)
        if manual is not None:
            servings = recipe.servings if recipe.servings and recipe.servings > 0 else 1
            totals = manual.scale(Decimal(servings))
            return RecipeMacroBreakdown(lines=[], totals=totals, per_serving=manual)

        lines = [self.line_profile(line, nutrient_index) for line in recipe.ingredients]

        totals = MacroProfile({})
        for line in lines:
            totals = totals + line.profile

        per_serving = None
        if recipe.servings and recipe.servings > 0:
            divisor = Decimal(recipe.servings)
            per_serving = MacroProfile(
                {nutrient: amount / divisor for nutrient, amount in totals.amounts.items()}
            )

        return RecipeMacroBreakdown(lines=lines, totals=totals, per_serving=per_serving)
