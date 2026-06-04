"""Pydantic models for the shopping-list HTTP boundary."""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from recetario.domain.entities import ShoppingList, ShoppingListItem, ShoppingListStatus


class GenerateShoppingListRequest(BaseModel):
    week_start: Date
    week_end: Date
    name: str | None = None


class ToggleItemRequest(BaseModel):
    checked: bool


class ShoppingItemOut(BaseModel):
    id: int
    ingredient_id: int | None
    ingredient_name: str
    unit: str | None
    total_quantity: Decimal | None
    checked: bool
    source_event_ids: list[int]
    external_task_id: str | None

    @classmethod
    def from_domain(cls, item: ShoppingListItem) -> "ShoppingItemOut":
        return cls(
            id=item.id,
            ingredient_id=item.ingredient_id,
            ingredient_name=item.ingredient_name,
            unit=item.unit,
            total_quantity=item.total_quantity,
            checked=item.checked,
            source_event_ids=item.source_event_ids,
            external_task_id=item.external_task_id,
        )


class ShoppingListOut(BaseModel):
    id: int
    name: str
    week_start: Date
    week_end: Date
    status: ShoppingListStatus
    generated_at: datetime | None
    external_tasklist_id: str | None
    items: list[ShoppingItemOut]

    @classmethod
    def from_domain(cls, sl: ShoppingList) -> "ShoppingListOut":
        return cls(
            id=sl.id,
            name=sl.name,
            week_start=sl.week_start,
            week_end=sl.week_end,
            status=sl.status,
            generated_at=sl.generated_at,
            external_tasklist_id=sl.external_tasklist_id,
            items=[ShoppingItemOut.from_domain(i) for i in sl.items],
        )


class ShoppingListSummary(BaseModel):
    """Lightweight list-view row: counts instead of the full item set."""

    id: int
    name: str
    week_start: Date
    week_end: Date
    status: ShoppingListStatus
    generated_at: datetime | None
    item_count: int
    checked_count: int

    @classmethod
    def from_domain(cls, sl: ShoppingList) -> "ShoppingListSummary":
        return cls(
            id=sl.id,
            name=sl.name,
            week_start=sl.week_start,
            week_end=sl.week_end,
            status=sl.status,
            generated_at=sl.generated_at,
            item_count=len(sl.items),
            checked_count=sum(1 for i in sl.items if i.checked),
        )
