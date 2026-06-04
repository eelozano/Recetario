"""Nutrition value objects. Used from Phase 2 onward by the MacroCalculator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class NutrientAmount:
    nutrient: str
    amount: Decimal
    unit: str


@dataclass(frozen=True)
class MacroProfile:
    """An immutable, additive bundle of nutrient amounts (per recipe, line, or meal)."""

    amounts: dict[str, Decimal]

    def __add__(self, other: MacroProfile) -> MacroProfile:
        merged = dict(self.amounts)
        for nutrient, amount in other.amounts.items():
            merged[nutrient] = merged.get(nutrient, Decimal(0)) + amount
        return MacroProfile(merged)

    def scale(self, factor: Decimal) -> MacroProfile:
        """Multiply every nutrient amount by `factor` (e.g. servings planned)."""
        return MacroProfile({nutrient: amount * factor for nutrient, amount in self.amounts.items()})
