"""Shopping-list repository port — the persistence boundary for grocery lists."""

from __future__ import annotations

from typing import Protocol

from recetario.domain.entities import ShoppingList, ShoppingListItem, ShoppingListStatus


class ShoppingListRepository(Protocol):
    def add(self, shopping_list: ShoppingList) -> ShoppingList: ...

    def get(self, list_id: int) -> ShoppingList | None: ...

    def list(self) -> list[ShoppingList]: ...

    def delete(self, list_id: int) -> bool: ...

    def set_item_checked(self, item_id: int, checked: bool) -> ShoppingListItem | None: ...

    def apply_export(
        self,
        list_id: int,
        *,
        tasklist_id: str,
        item_task_ids: dict[int, str],
        status: ShoppingListStatus = ShoppingListStatus.EXPORTED,
    ) -> ShoppingList | None: ...
