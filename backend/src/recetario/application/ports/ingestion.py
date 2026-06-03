"""Ingestion ports — the boundaries the ingestion use cases depend on.

`RecipeScraper` turns a source URL into a structured draft (`RecipeInput`); the
deterministic adapter uses recipe-scrapers/JSON-LD, and a later LLM adapter can
implement the same port for messy pages. `IngestionJobRepository` persists job
state so the API can poll progress.
"""

from __future__ import annotations

from typing import Protocol

from recetario.application.dto import RecipeInput
from recetario.domain.entities import IngestionJob


class ScrapeError(Exception):
    """Raised when a source URL cannot be fetched or parsed into a recipe."""


class RecipeScraper(Protocol):
    def scrape(self, url: str) -> RecipeInput: ...


class IngestionJobRepository(Protocol):
    def add(self, job: IngestionJob) -> IngestionJob: ...

    def get(self, job_id: int) -> IngestionJob | None: ...

    def update(self, job: IngestionJob) -> IngestionJob | None: ...

    def list(self) -> list[IngestionJob]: ...
