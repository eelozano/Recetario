"""SQLAlchemy adapter for the USDA FDC cache (implements NutritionRepository).

Reads/writes the usda_foods / usda_food_nutrients / usda_food_portions tables and
the shared `nutrients` reference table. The macro math reads exclusively from here,
so the app works offline once the cache is seeded.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from recetario.application.dto.nutrition_dto import (
    FoodDetail,
    FoodNutrient,
    FoodPortion,
    FoodSummary,
)
from recetario.domain.value_objects.macro import NutrientAmount
from recetario.infrastructure.db.models import (
    NutrientModel,
    UsdaFoodModel,
    UsdaFoodNutrientModel,
    UsdaFoodPortionModel,
)


class SqlAlchemyNutritionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _get_or_create_nutrient(self, fn: FoodNutrient) -> NutrientModel:
        existing = self._session.scalar(
            select(NutrientModel).where(NutrientModel.usda_nutrient_id == fn.usda_nutrient_id)
        )
        if existing is not None:
            return existing
        model = NutrientModel(usda_nutrient_id=fn.usda_nutrient_id, name=fn.name, unit=fn.unit)
        self._session.add(model)
        self._session.flush()
        return model

    def upsert_food(self, detail: FoodDetail) -> None:
        food = self._session.get(UsdaFoodModel, detail.fdc_id)
        if food is None:
            food = UsdaFoodModel(fdc_id=detail.fdc_id)
            self._session.add(food)
        food.description = detail.description
        food.data_type = detail.data_type
        food.category = detail.category

        # Replace nutrient + portion rows wholesale so re-seeding stays idempotent.
        food.nutrients = [
            UsdaFoodNutrientModel(
                nutrient=self._get_or_create_nutrient(fn),
                amount=fn.amount,
                unit_name=fn.unit,
            )
            for fn in detail.nutrients
        ]
        food.portions = [
            UsdaFoodPortionModel(
                portion_description=fp.description,
                gram_weight=fp.gram_weight,
            )
            for fp in detail.portions
        ]
        self._session.commit()

    def _load(self, fdc_id: int) -> UsdaFoodModel | None:
        return self._session.scalar(
            select(UsdaFoodModel)
            .where(UsdaFoodModel.fdc_id == fdc_id)
            .options(
                selectinload(UsdaFoodModel.nutrients).selectinload(UsdaFoodNutrientModel.nutrient),
                selectinload(UsdaFoodModel.portions),
            )
        )

    def get_food(self, fdc_id: int) -> FoodDetail | None:
        model = self._load(fdc_id)
        if model is None:
            return None
        return FoodDetail(
            fdc_id=model.fdc_id,
            description=model.description,
            data_type=model.data_type,
            category=model.category,
            nutrients=[
                FoodNutrient(
                    usda_nutrient_id=n.nutrient.usda_nutrient_id,
                    name=n.nutrient.name,
                    unit=n.unit_name or n.nutrient.unit,
                    amount=n.amount,
                )
                for n in model.nutrients
            ],
            portions=[
                FoodPortion(gram_weight=p.gram_weight, description=p.portion_description)
                for p in model.portions
            ],
        )

    def search_cached(self, query: str, *, limit: int = 20) -> list[FoodSummary]:
        stmt = (
            select(UsdaFoodModel)
            .where(UsdaFoodModel.description.ilike(f"%{query}%"))
            .order_by(UsdaFoodModel.description)
            .limit(limit)
        )
        return [
            FoodSummary(fdc_id=m.fdc_id, description=m.description, data_type=m.data_type)
            for m in self._session.scalars(stmt)
        ]

    def nutrient_amounts(self, fdc_ids: list[int]) -> dict[int, list[NutrientAmount]]:
        if not fdc_ids:
            return {}
        stmt = (
            select(UsdaFoodNutrientModel)
            .where(UsdaFoodNutrientModel.fdc_id.in_(fdc_ids))
            .options(selectinload(UsdaFoodNutrientModel.nutrient))
        )
        result: dict[int, list[NutrientAmount]] = {fid: [] for fid in fdc_ids}
        for row in self._session.scalars(stmt):
            result[row.fdc_id].append(
                NutrientAmount(
                    nutrient=row.nutrient.name,
                    amount=row.amount,
                    unit=row.unit_name or row.nutrient.unit,
                )
            )
        return result
