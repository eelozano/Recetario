"""Pydantic request/response models for the HTTP boundary.

These map to/from the framework-agnostic application DTOs and domain entities.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.domain.entities import Recipe, RecipeStatus, SourceType


class IngredientLineIn(BaseModel):
    name: str = Field(min_length=1)
    quantity: Decimal | None = None
    unit: str | None = None
    raw_text: str | None = None
    notes: str | None = None


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    source_url: str | None = None
    source_type: SourceType = SourceType.MANUAL
    servings: int | None = Field(default=None, ge=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    status: RecipeStatus = RecipeStatus.DRAFT
    instructions_md: str | None = None
    ingredients: list[IngredientLineIn] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def to_input(self) -> RecipeInput:
        return RecipeInput(
            title=self.title,
            description=self.description,
            source_url=self.source_url,
            source_type=self.source_type,
            servings=self.servings,
            rating=self.rating,
            status=self.status,
            instructions_md=self.instructions_md,
            ingredients=[
                RecipeIngredientInput(
                    name=line.name,
                    quantity=line.quantity,
                    unit=line.unit,
                    raw_text=line.raw_text,
                    notes=line.notes,
                )
                for line in self.ingredients
            ],
            tags=self.tags,
        )


class IngredientLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str
    quantity: Decimal | None = None
    unit: str | None = None
    raw_text: str | None = None
    notes: str | None = None
    usda_fdc_id: int | None = None
    gram_weight: Decimal | None = None


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str


class RecipeOut(BaseModel):
    id: int
    title: str
    description: str | None
    source_url: str | None
    source_type: SourceType
    servings: int | None
    rating: int | None
    status: RecipeStatus
    instructions_md: str | None
    ingredients: list[IngredientLineOut]
    tags: list[TagOut]

    @classmethod
    def from_domain(cls, recipe: Recipe) -> "RecipeOut":
        return cls(
            id=recipe.id,
            title=recipe.title,
            description=recipe.description,
            source_url=recipe.source_url,
            source_type=recipe.source_type,
            servings=recipe.servings,
            rating=recipe.rating,
            status=recipe.status,
            instructions_md=recipe.instructions_md,
            ingredients=[
                IngredientLineOut(
                    id=line.id,
                    name=line.ingredient.name,
                    quantity=line.quantity,
                    unit=line.unit,
                    raw_text=line.raw_text,
                    notes=line.notes,
                    usda_fdc_id=line.usda_fdc_id,
                    gram_weight=line.gram_weight,
                )
                for line in recipe.ingredients
            ],
            tags=[TagOut(id=t.id, name=t.name) for t in recipe.tags],
        )


class RecipeSummary(BaseModel):
    id: int
    title: str
    status: RecipeStatus
    rating: int | None
    servings: int | None
    tags: list[str]

    @classmethod
    def from_domain(cls, recipe: Recipe) -> "RecipeSummary":
        return cls(
            id=recipe.id,
            title=recipe.title,
            status=recipe.status,
            rating=recipe.rating,
            servings=recipe.servings,
            tags=[t.name for t in recipe.tags],
        )
