"""Nutrition endpoints: macro breakdown, manual USDA linking, cached food search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from recetario.api import deps
from recetario.api.schemas import (
    FoodSummaryOut,
    LinkIngredientRequest,
    MacroBreakdownOut,
    RecipeOut,
)
from recetario.application.use_cases.nutrition import (
    CalculateRecipeMacros,
    FoodNotCachedError,
    IngredientLineNotFoundError,
    LinkIngredientInput,
    LinkRecipeIngredientToUsda,
    SearchCachedFoods,
)
from recetario.application.use_cases.recipes import RecipeNotFoundError

router = APIRouter(tags=["nutrition"])


@router.get("/recipes/{recipe_id}/macros", response_model=MacroBreakdownOut)
def recipe_macros(
    recipe_id: int,
    uc: CalculateRecipeMacros = Depends(deps.calculate_macros_uc),
):
    try:
        return MacroBreakdownOut.from_domain(uc(recipe_id))
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


@router.post("/recipes/{recipe_id}/ingredients/{position}/link", response_model=RecipeOut)
def link_ingredient(
    recipe_id: int,
    position: int,
    payload: LinkIngredientRequest,
    uc: LinkRecipeIngredientToUsda = Depends(deps.link_ingredient_uc),
):
    try:
        recipe = uc(
            LinkIngredientInput(
                recipe_id=recipe_id,
                position=position,
                fdc_id=payload.fdc_id,
                gram_weight=payload.gram_weight,
            )
        )
    except RecipeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    except IngredientLineNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient line not found")
    except FoodNotCachedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"USDA food {exc.fdc_id} is not cached; seed it first",
        )
    return RecipeOut.from_domain(recipe)


@router.get("/foods/search", response_model=list[FoodSummaryOut])
def search_foods(
    query: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    uc: SearchCachedFoods = Depends(deps.search_foods_uc),
):
    return [FoodSummaryOut.from_dto(f) for f in uc(query, limit=limit)]
