"""Pydantic models for the nutrition / macro HTTP boundary."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from recetario.application.dto.nutrition_dto import FoodSummary
from recetario.domain.services.macro_calculator import LineMacro, RecipeMacroBreakdown


class LinkIngredientRequest(BaseModel):
    fdc_id: int
    gram_weight: Decimal = Field(gt=0)


class FoodSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fdc_id: int
    description: str
    data_type: str | None = None

    @classmethod
    def from_dto(cls, dto: FoodSummary) -> "FoodSummaryOut":
        return cls(fdc_id=dto.fdc_id, description=dto.description, data_type=dto.data_type)


class LineMacroOut(BaseModel):
    recipe_ingredient_id: int | None
    ingredient_name: str
    fdc_id: int | None
    gram_weight: Decimal | None
    resolved: bool
    macros: dict[str, Decimal]

    @classmethod
    def from_domain(cls, line: LineMacro) -> "LineMacroOut":
        return cls(
            recipe_ingredient_id=line.recipe_ingredient_id,
            ingredient_name=line.ingredient_name,
            fdc_id=line.fdc_id,
            gram_weight=line.gram_weight,
            resolved=line.resolved,
            macros=dict(line.profile.amounts),
        )


class MacroBreakdownOut(BaseModel):
    """Recipe totals + the per-ingredient breakdown (the diagnostics view)."""

    totals: dict[str, Decimal]
    per_serving: dict[str, Decimal] | None
    unresolved_count: int
    lines: list[LineMacroOut]

    @classmethod
    def from_domain(cls, breakdown: RecipeMacroBreakdown) -> "MacroBreakdownOut":
        return cls(
            totals=dict(breakdown.totals.amounts),
            per_serving=(
                dict(breakdown.per_serving.amounts) if breakdown.per_serving is not None else None
            ),
            unresolved_count=breakdown.unresolved_count,
            lines=[LineMacroOut.from_domain(line) for line in breakdown.lines],
        )
