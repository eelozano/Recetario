"""Pure domain entities — no framework, no ORM, no I/O.

These are the canonical in-memory representations the business logic operates on.
Repositories map persistence rows to/from these objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class SourceType(str, Enum):
    WEB = "web"
    VIDEO = "video"
    MANUAL = "manual"


class RecipeStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"


@dataclass
class Tag:
    name: str
    id: int | None = None


@dataclass
class Ingredient:
    """A canonical, deduplicated ingredient in the user's catalog."""

    name: str
    normalized_name: str
    id: int | None = None
    usda_fdc_id: int | None = None
    default_unit: str | None = None


@dataclass
class RecipeIngredient:
    """A single ingredient line on a recipe — the ingredient-level macro link.

    `usda_fdc_id` and `gram_weight` are populated by the nutrition-resolution step
    (Phase 2/3) and drive per-ingredient macro math.
    """

    ingredient: Ingredient
    quantity: Decimal | None = None
    unit: str | None = None
    raw_text: str | None = None
    position: int = 0
    usda_fdc_id: int | None = None
    gram_weight: Decimal | None = None
    notes: str | None = None
    id: int | None = None


@dataclass
class Recipe:
    title: str
    id: int | None = None
    description: str | None = None
    source_url: str | None = None
    source_type: SourceType = SourceType.MANUAL
    servings: int | None = None
    rating: int | None = None
    status: RecipeStatus = RecipeStatus.DRAFT
    instructions_md: str | None = None
    # Recipe-level macros, entered by hand per serving. These are the primary
    # macro source: when any is set, the MacroCalculator uses them directly
    # instead of summing ingredient-level USDA links (see macro_calculator).
    calories_per_serving: Decimal | None = None
    protein_per_serving: Decimal | None = None
    fat_per_serving: Decimal | None = None
    carbs_per_serving: Decimal | None = None
    fiber_per_serving: Decimal | None = None
    sodium_per_serving: Decimal | None = None
    ingredients: list[RecipeIngredient] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
