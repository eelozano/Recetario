"""Plain DTOs for nutrition data crossing the application boundary.

Framework-free dataclasses so the core never depends on httpx, Pydantic, or
SQLAlchemy. The FDC adapter and the nutrition repository both speak these.
Nutrient amounts are always on a per-100g basis (the FDC convention).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class FoodNutrient:
    usda_nutrient_id: int
    name: str
    unit: str
    amount: Decimal  # per 100 g of the food


@dataclass
class FoodPortion:
    gram_weight: Decimal
    description: str | None = None


@dataclass
class FoodSummary:
    """A lightweight search hit, before fetching full nutrient detail."""

    fdc_id: int
    description: str
    data_type: str | None = None


@dataclass
class FoodDetail:
    fdc_id: int
    description: str
    data_type: str | None = None
    category: str | None = None
    nutrients: list[FoodNutrient] = field(default_factory=list)
    portions: list[FoodPortion] = field(default_factory=list)
