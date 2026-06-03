"""Recipe-ingestion use cases.

`StartUrlIngestion` records a queued job and returns immediately; the API then
runs `RunUrlIngestion` in the background. The split keeps the request fast and
lets the worker graduate to a real queue later without changing the API.
"""

from __future__ import annotations

from recetario.application.dto import RecipeInput
from recetario.application.ports import (
    ExtractError,
    IngestionJobRepository,
    LlmRecipeExtractor,
    NutritionProvider,
    NutritionRepository,
    RecipeScraper,
    ScrapeError,
)
from recetario.application.use_cases.recipes import CreateRecipe
from recetario.domain.entities import IngestionInputType, IngestionJob


class IngestionJobNotFoundError(Exception):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Ingestion job {job_id} not found")
        self.job_id = job_id


class EnrichDraftRecipe:
    """Refine a scraped draft with the LLM, then resolve USDA matches.

    Best-effort by design: each phase is guarded so a Claude or FDC hiccup
    degrades to the deterministic draft rather than failing the ingestion job.
    Only matches at or above `min_confidence` are linked (and their chosen food
    upserted into the local cache); weaker or absent matches are left unlinked so
    the user confirms them through the existing manual-link flow.
    """

    def __init__(
        self,
        extractor: LlmRecipeExtractor,
        provider: NutritionProvider,
        nutrition: NutritionRepository,
        *,
        min_confidence: float = 0.6,
    ) -> None:
        self._extractor = extractor
        self._provider = provider
        self._nutrition = nutrition
        self._min_confidence = min_confidence

    def __call__(self, draft: RecipeInput) -> RecipeInput:
        try:
            structured = self._extractor.structure(draft)
        except ExtractError:
            structured = draft

        try:
            resolved = self._extractor.resolve_nutrition(
                structured.ingredients, self._provider
            )
        except ExtractError:
            return structured

        for match in resolved:
            if match.fdc_id is None or match.confidence < self._min_confidence:
                continue
            if not 0 <= match.index < len(structured.ingredients):
                continue
            detail = self._nutrition.get_food(match.fdc_id) or self._provider.get_food(
                match.fdc_id
            )
            if detail is None:
                continue
            self._nutrition.upsert_food(detail)
            line = structured.ingredients[match.index]
            line.usda_fdc_id = match.fdc_id
            line.gram_weight = match.gram_weight

        return structured


class StartUrlIngestion:
    """Persist a queued job for a URL import. The actual work runs separately."""

    def __init__(self, jobs: IngestionJobRepository) -> None:
        self._jobs = jobs

    def __call__(self, url: str) -> IngestionJob:
        job = IngestionJob(input_url=url.strip(), input_type=IngestionInputType.WEB)
        return self._jobs.add(job)


class RunUrlIngestion:
    """Execute a queued job: scrape the URL → persist a draft recipe → finish.

    Always resolves the job to a terminal state (succeeded/failed); scrape and
    persistence failures are captured on the job rather than raised, so the
    background worker never crashes silently.
    """

    def __init__(
        self,
        jobs: IngestionJobRepository,
        create_recipe: CreateRecipe,
        scraper: RecipeScraper,
        enrich: EnrichDraftRecipe | None = None,
    ) -> None:
        self._jobs = jobs
        self._create_recipe = create_recipe
        self._scraper = scraper
        self._enrich = enrich

    def __call__(self, job_id: int) -> IngestionJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)

        job.mark_running()
        self._jobs.update(job)

        try:
            draft = self._scraper.scrape(job.input_url)
            if self._enrich is not None:
                draft = self._enrich(draft)
            recipe = self._create_recipe(draft)
            assert recipe.id is not None
            job.mark_succeeded(recipe.id)
        except ScrapeError as exc:
            job.mark_failed(str(exc))
        except Exception as exc:  # noqa: BLE001 - record any failure on the job
            job.mark_failed(f"Unexpected error: {exc}")

        updated = self._jobs.update(job)
        return updated or job


class GetIngestionJob:
    def __init__(self, jobs: IngestionJobRepository) -> None:
        self._jobs = jobs

    def __call__(self, job_id: int) -> IngestionJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)
        return job


class ListIngestionJobs:
    def __init__(self, jobs: IngestionJobRepository) -> None:
        self._jobs = jobs

    def __call__(self) -> list[IngestionJob]:
        return self._jobs.list()
