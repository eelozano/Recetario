"""Composition root — wires concrete adapters into the API via FastAPI Depends.

The engine/session factory lives on app.state so tests can swap in an in-memory DB
by overriding `get_session`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from recetario.application.use_cases.ingestion import (
    GetIngestionJob,
    ListIngestionJobs,
    StartUrlIngestion,
)
from recetario.application.use_cases.nutrition import (
    CalculateRecipeMacros,
    LinkRecipeIngredientToUsda,
    SearchCachedFoods,
)
from recetario.application.use_cases.recipes import (
    CreateRecipe,
    DeleteRecipe,
    GetRecipe,
    ListRecipes,
    UpdateRecipe,
)
from recetario.domain.services.macro_calculator import MacroCalculator
from recetario.infrastructure.db.repositories import (
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyNutritionRepository,
    SqlAlchemyRecipeRepository,
    SqlAlchemyTagRepository,
)


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_recipe_repository(session: Session = Depends(get_session)) -> SqlAlchemyRecipeRepository:
    return SqlAlchemyRecipeRepository(session)


def get_tag_repository(session: Session = Depends(get_session)) -> SqlAlchemyTagRepository:
    return SqlAlchemyTagRepository(session)


def get_nutrition_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyNutritionRepository:
    return SqlAlchemyNutritionRepository(session)


def get_ingestion_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyIngestionJobRepository:
    return SqlAlchemyIngestionJobRepository(session)


def create_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return CreateRecipe(repo)


def get_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return GetRecipe(repo)


def list_recipes_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return ListRecipes(repo)


def update_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return UpdateRecipe(repo)


def delete_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return DeleteRecipe(repo)


def calculate_macros_uc(
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> CalculateRecipeMacros:
    return CalculateRecipeMacros(recipes, nutrition, MacroCalculator())


def link_ingredient_uc(
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> LinkRecipeIngredientToUsda:
    return LinkRecipeIngredientToUsda(recipes, nutrition)


def search_foods_uc(
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> SearchCachedFoods:
    return SearchCachedFoods(nutrition)


def start_ingestion_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> StartUrlIngestion:
    return StartUrlIngestion(jobs)


def get_ingestion_job_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> GetIngestionJob:
    return GetIngestionJob(jobs)


def list_ingestion_jobs_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> ListIngestionJobs:
    return ListIngestionJobs(jobs)
