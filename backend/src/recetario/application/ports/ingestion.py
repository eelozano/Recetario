"""Ingestion ports — the boundaries the ingestion use cases depend on.

`RecipeScraper` turns a source URL into a structured draft (`RecipeInput`); the
deterministic adapter uses recipe-scrapers/JSON-LD, and a later LLM adapter can
implement the same port for messy pages. `LlmRecipeExtractor` is the optional
LLM layer that refines that draft (parsing quantities/units) and matches each
ingredient line to a USDA food. `IngestionJobRepository` persists job state so
the API can poll progress.
"""

from __future__ import annotations

from typing import Protocol

from recetario.application.dto import RecipeIngredientInput, RecipeInput, ResolvedIngredient
from recetario.application.ports.nutrition import NutritionProvider
from recetario.domain.entities import IngestionJob


class ScrapeError(Exception):
    """Raised when a source URL cannot be fetched or parsed into a recipe."""


class ExtractError(Exception):
    """Raised when the LLM extractor cannot structure or resolve a draft.

    Enrichment is best-effort, so callers catch this and fall back to the
    deterministic draft rather than failing the whole ingestion job.
    """


class RecipeScraper(Protocol):
    def scrape(self, url: str) -> RecipeInput: ...


class LlmRecipeExtractor(Protocol):
    """The LLM decisions only — retrieval and persistence stay in the use case.

    `structure` refines a scraped draft (parsing each ingredient line into
    quantity/unit/name and tidying title/servings). `resolve_nutrition` matches
    each line to a USDA food, using the live `search` provider to look up
    candidates, and reports a per-line confidence so low matches can be deferred.
    """

    def structure(self, draft: RecipeInput) -> RecipeInput: ...

    def resolve_nutrition(
        self,
        ingredients: list[RecipeIngredientInput],
        search: NutritionProvider,
    ) -> list[ResolvedIngredient]: ...


class IngestionJobRepository(Protocol):
    def add(self, job: IngestionJob) -> IngestionJob: ...

    def get(self, job_id: int) -> IngestionJob | None: ...

    def update(self, job: IngestionJob) -> IngestionJob | None: ...

    def list(self) -> list[IngestionJob]: ...
