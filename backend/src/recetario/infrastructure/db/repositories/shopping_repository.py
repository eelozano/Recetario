"""SQLAlchemy adapter implementing ShoppingListRepository.

Maps shopping_lists / shopping_list_items rows ↔ domain objects. `generated_at`
is surfaced from the row's created_at (we don't keep a separate column).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from recetario.domain.entities import ShoppingList, ShoppingListItem, ShoppingListStatus
from recetario.identity import DEFAULT_OWNER_ID
from recetario.infrastructure.db.models import ShoppingListItemModel, ShoppingListModel


def _item_to_domain(model: ShoppingListItemModel) -> ShoppingListItem:
    return ShoppingListItem(
        id=model.id,
        ingredient_id=model.ingredient_id,
        ingredient_name=model.ingredient_name,
        unit=model.unit,
        total_quantity=model.total_quantity,
        checked=model.checked,
        external_task_id=model.external_task_id,
        source_event_ids=list(model.source_event_ids or []),
    )


def _to_domain(model: ShoppingListModel) -> ShoppingList:
    return ShoppingList(
        id=model.id,
        name=model.name,
        week_start=model.week_start,
        week_end=model.week_end,
        status=ShoppingListStatus(model.status),
        items=[_item_to_domain(i) for i in model.items],
        external_tasklist_id=model.external_tasklist_id,
        generated_at=model.created_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyShoppingListRepository:
    def __init__(self, session: Session, *, owner_id: int = DEFAULT_OWNER_ID) -> None:
        self._session = session
        self._owner_id = owner_id

    def add(self, shopping_list: ShoppingList) -> ShoppingList:
        model = ShoppingListModel(
            owner_id=self._owner_id,
            name=shopping_list.name,
            week_start=shopping_list.week_start,
            week_end=shopping_list.week_end,
            status=shopping_list.status.value,
            items=[
                ShoppingListItemModel(
                    ingredient_id=item.ingredient_id,
                    ingredient_name=item.ingredient_name,
                    unit=item.unit,
                    total_quantity=item.total_quantity,
                    checked=item.checked,
                    external_task_id=item.external_task_id,
                    source_event_ids=item.source_event_ids or None,
                )
                for item in shopping_list.items
            ],
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def _load(self, list_id: int) -> ShoppingListModel | None:
        return self._session.scalar(
            select(ShoppingListModel)
            .where(
                ShoppingListModel.id == list_id,
                ShoppingListModel.owner_id == self._owner_id,
            )
            .options(selectinload(ShoppingListModel.items))
        )

    def get(self, list_id: int) -> ShoppingList | None:
        model = self._load(list_id)
        return _to_domain(model) if model else None

    def list(self) -> list[ShoppingList]:
        stmt = (
            select(ShoppingListModel)
            .where(ShoppingListModel.owner_id == self._owner_id)
            .options(selectinload(ShoppingListModel.items))
            .order_by(ShoppingListModel.created_at.desc())
        )
        return [_to_domain(m) for m in self._session.scalars(stmt)]

    def delete(self, list_id: int) -> bool:
        model = self._load(list_id)  # owner-scoped
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True

    def apply_export(
        self,
        list_id: int,
        *,
        tasklist_id: str,
        item_task_ids: dict[int, str],
        status: ShoppingListStatus = ShoppingListStatus.EXPORTED,
    ) -> ShoppingList | None:
        """Persist the outcome of an export: the external tasklist id, per-item
        external task ids, and the list's status."""
        model = self._load(list_id)
        if model is None:
            return None
        model.external_tasklist_id = tasklist_id
        model.status = status.value
        for item in model.items:
            external = item_task_ids.get(item.id)
            if external is not None:
                item.external_task_id = external
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def set_item_checked(self, item_id: int, checked: bool) -> ShoppingListItem | None:
        # Scope through the parent list's owner so you can't toggle another
        # owner's item by guessing its id.
        model = self._session.scalar(
            select(ShoppingListItemModel)
            .join(ShoppingListModel)
            .where(
                ShoppingListItemModel.id == item_id,
                ShoppingListModel.owner_id == self._owner_id,
            )
        )
        if model is None:
            return None
        model.checked = checked
        self._session.commit()
        self._session.refresh(model)
        return _item_to_domain(model)
