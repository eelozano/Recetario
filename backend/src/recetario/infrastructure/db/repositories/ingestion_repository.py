"""SQLAlchemy adapter implementing the IngestionJobRepository port."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from recetario.domain.entities import IngestionInputType, IngestionJob, JobStatus
from recetario.infrastructure.db.models import IngestionJobModel


def _to_domain(model: IngestionJobModel) -> IngestionJob:
    return IngestionJob(
        id=model.id,
        input_url=model.input_url,
        input_type=IngestionInputType(model.input_type),
        status=JobStatus(model.status),
        progress=model.progress,
        result_recipe_id=model.result_recipe_id,
        error=model.error,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _apply(model: IngestionJobModel, job: IngestionJob) -> None:
    model.input_url = job.input_url
    model.input_type = job.input_type.value
    model.status = job.status.value
    model.progress = job.progress
    model.result_recipe_id = job.result_recipe_id
    model.error = job.error


class SqlAlchemyIngestionJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, job: IngestionJob) -> IngestionJob:
        model = IngestionJobModel()
        _apply(model, job)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def get(self, job_id: int) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        return _to_domain(model) if model else None

    def update(self, job: IngestionJob) -> IngestionJob | None:
        assert job.id is not None
        model = self._session.get(IngestionJobModel, job.id)
        if model is None:
            return None
        _apply(model, job)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def list(self) -> list[IngestionJob]:
        rows = self._session.scalars(
            select(IngestionJobModel).order_by(IngestionJobModel.created_at.desc())
        )
        return [_to_domain(m) for m in rows]
