"""Shopping-list endpoints. Generate a week's list, view it, check items off."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from recetario.api import deps
from recetario.api.schemas import (
    GenerateShoppingListRequest,
    ShoppingItemOut,
    ShoppingListOut,
    ShoppingListSummary,
    ToggleItemRequest,
)
from recetario.application.use_cases.shopping import (
    DeleteShoppingList,
    GenerateWeeklyShoppingList,
    GetShoppingList,
    ListShoppingLists,
    ShoppingItemNotFoundError,
    ShoppingListNotFoundError,
    ToggleShoppingItem,
)

router = APIRouter(prefix="/shopping-lists", tags=["shopping"])


@router.post("", response_model=ShoppingListOut, status_code=status.HTTP_201_CREATED)
def generate_shopping_list(
    payload: GenerateShoppingListRequest,
    uc: GenerateWeeklyShoppingList = Depends(deps.generate_shopping_uc),
):
    if payload.week_end < payload.week_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`week_end` must be on or after `week_start`",
        )
    sl = uc(payload.week_start, payload.week_end, name=payload.name)
    return ShoppingListOut.from_domain(sl)


@router.get("", response_model=list[ShoppingListSummary])
def list_shopping_lists(uc: ListShoppingLists = Depends(deps.list_shopping_uc)):
    return [ShoppingListSummary.from_domain(sl) for sl in uc()]


@router.get("/{list_id}", response_model=ShoppingListOut)
def get_shopping_list(list_id: int, uc: GetShoppingList = Depends(deps.get_shopping_uc)):
    try:
        return ShoppingListOut.from_domain(uc(list_id))
    except ShoppingListNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_list(list_id: int, uc: DeleteShoppingList = Depends(deps.delete_shopping_uc)):
    try:
        uc(list_id)
    except ShoppingListNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")


@router.patch("/{list_id}/items/{item_id}", response_model=ShoppingItemOut)
def toggle_item(
    list_id: int,
    item_id: int,
    payload: ToggleItemRequest,
    uc: ToggleShoppingItem = Depends(deps.toggle_item_uc),
):
    try:
        return ShoppingItemOut.from_domain(uc(item_id, payload.checked))
    except ShoppingItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
