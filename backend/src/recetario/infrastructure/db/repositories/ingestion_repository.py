"""SQLAlchemy adapter implementing the IngestionJobRepository port."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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
        try:
            return self._write(job)
        except SQLAlchemyError:
            # The ingestion worker shares one session across repos, so a sibling
            # (e.g. a failed USDA nutrient upsert) can poison the transaction and
            # leave it unusable. Roll back and retry once so the job's terminal
            # status (notably 'failed') is always recorded — otherwise the job
            # would wedge in 'running' forever. Safe here because every repo
            # commits eagerly, so the rollback only discards the already-failed
            # in-flight work, never legitimate uncommitted state.
            self._session.rollback()
            return self._write(job)

    def _write(self, job: IngestionJob) -> IngestionJob | None:
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
