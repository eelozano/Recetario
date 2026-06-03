"""Recipe-ingestion use cases.

`StartUrlIngestion` records a queued job and returns immediately; the API then
runs `RunUrlIngestion` (web) or `RunVideoIngestion` (video) in the background.
The split keeps the request fast and lets the worker graduate to a real queue
later without changing the API.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from recetario.application.dto import RecipeInput
from recetario.application.ports import (
    ExtractError,
    IngestionJobRepository,
    LlmRecipeExtractor,
    NutritionProvider,
    NutritionRepository,
    RecipeScraper,
    ScrapeError,
    VideoTranscriptFetcher,
)
from recetario.application.use_cases.recipes import CreateRecipe
from recetario.domain.entities import IngestionInputType, IngestionJob

# Hosts whose URLs we treat as videos (captions → LLM) rather than web pages.
_VIDEO_HOSTS = (
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "tiktok.com",
    "instagram.com",
    "dailymotion.com",
    "facebook.com",
    "fb.watch",
)


def detect_input_type(url: str) -> IngestionInputType:
    """Classify a URL as VIDEO (known video host) or WEB (everything else)."""
    host = urlparse(url.strip()).netloc.lower()
    host = host.split("@")[-1].split(":")[0]  # strip credentials/port
    host = host.removeprefix("www.").removeprefix("m.")
    if any(host == h or host.endswith("." + h) for h in _VIDEO_HOSTS):
        return IngestionInputType.VIDEO
    return IngestionInputType.WEB


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
        return self.resolve(structured)

    def resolve(self, structured: RecipeInput) -> RecipeInput:
        """Match an already-structured draft to USDA foods (the second pass).

        Split out so the video path — whose draft is structured by the
        transcript-extraction pass — can reuse USDA matching without re-running
        the scraped-draft `structure` step.
        """
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
    """Persist a queued job for a URL import. The actual work runs separately.

    The input type (web vs video) is auto-detected from the URL host but can be
    overridden by the caller (e.g. an explicit `input_type` in the request).
    """

    def __init__(self, jobs: IngestionJobRepository) -> None:
        self._jobs = jobs

    def __call__(
        self, url: str, input_type: IngestionInputType | None = None
    ) -> IngestionJob:
        url = url.strip()
        job = IngestionJob(
            input_url=url,
            input_type=input_type or detect_input_type(url),
        )
        return self._jobs.add(job)


def _run_ingestion_job(
    jobs: IngestionJobRepository,
    create_recipe: CreateRecipe,
    job_id: int,
    produce_draft: Callable[[IngestionJob], RecipeInput],
) -> IngestionJob:
    """Drive a job to a terminal state around a source-specific draft producer.

    Marks the job running, calls `produce_draft` (scrape, or fetch+extract),
    persists the resulting recipe, and records success/failure on the job.
    Source errors (`ScrapeError`/`TranscriptError`) and extraction errors
    (`ExtractError`) become clean failure messages; anything else is captured
    generically so the background worker never crashes silently.
    """
    job = jobs.get(job_id)
    if job is None:
        raise IngestionJobNotFoundError(job_id)

    job.mark_running()
    jobs.update(job)

    try:
        draft = produce_draft(job)
        recipe = create_recipe(draft)
        assert recipe.id is not None
        job.mark_succeeded(recipe.id)
    except (ScrapeError, ExtractError) as exc:
        job.mark_failed(str(exc))
    except Exception as exc:  # noqa: BLE001 - record any failure on the job
        job.mark_failed(f"Unexpected error: {exc}")

    updated = jobs.update(job)
    return updated or job


class RunUrlIngestion:
    """Execute a queued web job: scrape the URL → enrich → persist a draft."""

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
        return _run_ingestion_job(
            self._jobs, self._create_recipe, job_id, self._produce
        )

    def _produce(self, job: IngestionJob) -> RecipeInput:
        draft = self._scraper.scrape(job.input_url)
        if self._enrich is not None:
            draft = self._enrich(draft)
        return draft


class RunVideoIngestion:
    """Execute a queued video job: fetch captions → LLM-extract → enrich.

    Unlike the web path, the LLM is required here (you cannot deterministically
    parse a transcript), so an extractor is mandatory. USDA matching via `enrich`
    stays optional and additive — when present, only its resolve pass runs, since
    the transcript extraction already produced a structured draft.
    """

    def __init__(
        self,
        jobs: IngestionJobRepository,
        create_recipe: CreateRecipe,
        fetcher: VideoTranscriptFetcher,
        extractor: LlmRecipeExtractor,
        enrich: EnrichDraftRecipe | None = None,
    ) -> None:
        self._jobs = jobs
        self._create_recipe = create_recipe
        self._fetcher = fetcher
        self._extractor = extractor
        self._enrich = enrich

    def __call__(self, job_id: int) -> IngestionJob:
        return _run_ingestion_job(
            self._jobs, self._create_recipe, job_id, self._produce
        )

    def _produce(self, job: IngestionJob) -> RecipeInput:
        transcript = self._fetcher.fetch_transcript(job.input_url)
        draft = self._extractor.extract_from_transcript(
            transcript, source_url=job.input_url
        )
        if self._enrich is not None:
            draft = self._enrich.resolve(draft)
        return draft


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
