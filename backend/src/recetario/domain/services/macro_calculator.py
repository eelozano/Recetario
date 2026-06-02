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
