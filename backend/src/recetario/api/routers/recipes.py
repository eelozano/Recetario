"""Recipe CRUD endpoints. Thin: validate, call a use case, map to a response schema."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from recetario.api import deps
from recetario.api.schemas import RecipeCreate, RecipeOut, RecipeSummary, TagOut
from recetario.application.use_cases.recipes import (
    CreateRecipe,
    DeleteRecipe,
    GetRecipe,
    ListRecipes,
    RecipeNotFoundError,
    UpdateRecipe,
)
from recetario.infrastructure.db.repositories import SqlAlchemyTagRepository

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(payload: RecipeCreate, uc: CreateRecipe = Depends(deps.create_recipe_uc)):
    return RecipeOut.from_domain(uc(payload.to_input()))


@router.get("", response_model=list[RecipeSummary])
def list_recipes(
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None),
    uc: ListRecipes = Depends(deps.list_recipes_uc),
):
    return [RecipeSummary.from_domain(r) for r in uc(tag=tag, search=search)]


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, uc: GetRecipe = Depends(deps.get_recipe_uc)):
    try:
        return RecipeOut.from_domain(uc(recipe_id))
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int,
    payload: RecipeCreate,
    uc: UpdateRecipe = Depends(deps.update_recipe_uc),
):
    try:
        return RecipeOut.from_domain(uc(recipe_id, payload.to_input()))
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, uc: DeleteRecipe = Depends(deps.delete_recipe_uc)):
    try:
        uc(recipe_id)
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


tags_router = APIRouter(prefix="/tags", tags=["tags"])


@tags_router.get("", response_model=list[TagOut])
def list_tags(repo: SqlAlchemyTagRepository = Depends(deps.get_tag_repository)):
    return [TagOut(id=t.id, name=t.name) for t in repo.list()]
