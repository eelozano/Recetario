"""Composition root — wires concrete adapters into the API via FastAPI Depends.

The engine/session factory lives on app.state so tests can swap in an in-memory DB
by overriding `get_session`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from recetario.application.use_cases.recipes import (
    CreateRecipe,
    DeleteRecipe,
    GetRecipe,
    ListRecipes,
    UpdateRecipe,
)
from recetario.infrastructure.db.repositories import (
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
