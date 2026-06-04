"""SQLAlchemy adapter implementing MealEventRepository.

Maps meal_events rows ↔ MealEvent domain objects. On read it eager-loads the
linked recipe (lazy="joined" on the model) and copies its title onto the entity
for the calendar view, without leaking the ORM.
"""

from __future__ import annotations

from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

from recetario.domain.entities import MealEvent, MealType
from recetario.identity import DEFAULT_OWNER_ID
from recetario.infrastructure.db.models import MealEventModel


def _to_domain(model: MealEventModel) -> MealEvent:
    return MealEvent(
        id=model.id,
        date=model.date,
        meal_type=MealType(model.meal_type),
        recipe_id=model.recipe_id,
        servings_planned=model.servings_planned,
        notes=model.notes,
        recipe_title=model.recipe.title if model.recipe is not None else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyMealEventRepository:
    def __init__(self, session: Session, *, owner_id: int = DEFAULT_OWNER_ID) -> None:
        self._session = session
        self._owner_id = owner_id

    def _apply(self, model: MealEventModel, event: MealEvent) -> None:
        model.date = event.date
        model.meal_type = event.meal_type.value
        model.recipe_id = event.recipe_id
        model.servings_planned = event.servings_planned
        model.notes = event.notes

    def _get(self, event_id: int) -> MealEventModel | None:
        return self._session.scalar(
            select(MealEventModel).where(
                MealEventModel.id == event_id,
                MealEventModel.owner_id == self._owner_id,
            )
        )

    def add(self, event: MealEvent) -> MealEvent:
        model = MealEventModel(owner_id=self._owner_id)
        self._apply(model, event)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def get(self, event_id: int) -> MealEvent | None:
        model = self._get(event_id)
        return _to_domain(model) if model else None

    def list_range(self, start: Date, end: Date) -> list[MealEvent]:
        stmt = (
            select(MealEventModel)
            .where(
                MealEventModel.owner_id == self._owner_id,
                MealEventModel.date >= start,
                MealEventModel.date <= end,
            )
            .order_by(MealEventModel.date, MealEventModel.id)
        )
        return [_to_domain(m) for m in self._session.scalars(stmt)]

    def update(self, event: MealEvent) -> MealEvent | None:
        assert event.id is not None
        model = self._get(event.id)
        if model is None:
            return None
        self._apply(model, event)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def delete(self, event_id: int) -> bool:
        model = self._get(event_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True
