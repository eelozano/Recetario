"""Framework-agnostic input DTOs for use cases.

Deliberately plain (not Pydantic) so the application layer carries no web-framework
dependency. The API layer validates with Pydantic, then maps into these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from recetario.domain.entities import RecipeStatus, SourceType


@dataclass
class RecipeIngredientInput:
    name: str
    quantity: Decimal | None = None
    unit: str | None = None
    raw_text: str | None = None
    notes: str | None = None


@dataclass
class RecipeInput:
    title: str
    description: str | None = None
    source_url: str | None = None
    source_type: SourceType = SourceType.MANUAL
    servings: int | None = None
    rating: int | None = None
    status: RecipeStatus = RecipeStatus.DRAFT
    instructions_md: str | None = None
    ingredients: list[RecipeIngredientInput] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
