"""Regression tests for SqlAlchemyNutritionRepository.upsert_food (issue #7).

FDC can report the same nutrient more than once for a food, and a re-upsert
replaces an existing food's child rows. Both must not violate the unique
(fdc_id, nutrient_id) index — that crash previously wedged the ingestion job.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from recetario.application.dto.nutrition_dto import FoodDetail, FoodNutrient, FoodPortion
from recetario.infrastructure.db.repositories import SqlAlchemyNutritionRepository

# USDA nutrient ids (energy appears under more than one Atwater variant in FDC).
ENERGY = 1008
PROTEIN = 1003


@pytest.fixture
def session(db_engine: Engine) -> Session:
    with Session(db_engine, future=True) as s:
        yield s


def test_upsert_food_dedups_duplicate_nutrients(session: Session) -> None:
    repo = SqlAlchemyNutritionRepository(session)
    detail = FoodDetail(
        fdc_id=173468,
        description="Beef broth, bouillon",
        nutrients=[
            FoodNutrient(usda_nutrient_id=ENERGY, name="Energy", unit="kcal", amount=Decimal("5")),
            # Same nutrient again — would collide on (fdc_id, nutrient_id).
            FoodNutrient(usda_nutrient_id=ENERGY, name="Energy", unit="kcal", amount=Decimal("0")),
            FoodNutrient(usda_nutrient_id=PROTEIN, name="Protein", unit="g", amount=Decimal("1")),
        ],
    )

    repo.upsert_food(detail)  # must not raise

    got = repo.get_food(173468)
    assert got is not None
    assert sorted(n.usda_nutrient_id for n in got.nutrients) == [PROTEIN, ENERGY]
    energy = next(n for n in got.nutrients if n.usda_nutrient_id == ENERGY)
    assert energy.amount == Decimal("5")  # first occurrence wins


def test_upsert_food_is_idempotent_on_reupsert(session: Session) -> None:
    repo = SqlAlchemyNutritionRepository(session)
    repo.upsert_food(
        FoodDetail(
            fdc_id=1,
            description="Onion v1",
            nutrients=[FoodNutrient(usda_nutrient_id=ENERGY, name="Energy", unit="kcal", amount=Decimal("40"))],
            portions=[FoodPortion(gram_weight=Decimal("110"), description="1 medium")],
        )
    )

    # Re-upsert the same food: the existing child rows must be replaced cleanly,
    # with no transient unique-index collision between old and new nutrient rows.
    repo.upsert_food(
        FoodDetail(
            fdc_id=1,
            description="Onion v2",
            nutrients=[FoodNutrient(usda_nutrient_id=ENERGY, name="Energy", unit="kcal", amount=Decimal("42"))],
            portions=[FoodPortion(gram_weight=Decimal("120"), description="1 large")],
        )
    )

    got = repo.get_food(1)
    assert got is not None
    assert got.description == "Onion v2"
    assert len(got.nutrients) == 1
    assert got.nutrients[0].amount == Decimal("42")
    assert len(got.portions) == 1
    assert got.portions[0].gram_weight == Decimal("120")
