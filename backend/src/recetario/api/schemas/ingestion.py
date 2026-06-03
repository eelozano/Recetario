"""Pydantic models for the ingestion (recipe-import) endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from recetario.domain.entities import IngestionInputType, IngestionJob, JobStatus


class IngestionJobCreate(BaseModel):
    url: str = Field(min_length=1, description="Recipe page URL to import.")


class IngestionJobOut(BaseModel):
    id: int
    input_url: str
    input_type: IngestionInputType
    status: JobStatus
    progress: int
    result_recipe_id: int | None
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_domain(cls, job: IngestionJob) -> "IngestionJobOut":
        return cls(
            id=job.id,
            input_url=job.input_url,
            input_type=job.input_type,
            status=job.status,
            progress=job.progress,
            result_recipe_id=job.result_recipe_id,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
