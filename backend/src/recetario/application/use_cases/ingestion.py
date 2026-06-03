"""Recipe-ingestion use cases.

`StartUrlIngestion` records a queued job and returns immediately; the API then
runs `RunUrlIngestion` in the background. The split keeps the request fast and
lets the worker graduate to a real queue later without changing the API.
"""

from __future__ import annotations

from recetario.application.ports import (
    IngestionJobRepository,
    RecipeScraper,
    ScrapeError,
)
from recetario.application.use_cases.recipes import CreateRecipe
from recetario.domain.entities import IngestionInputType, IngestionJob


class IngestionJobNotFoundError(Exception):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Ingestion job {job_id} not found")
        self.job_id = job_id


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
    ) -> None:
        self._jobs = jobs
        self._create_recipe = create_recipe
        self._scraper = scraper

    def __call__(self, job_id: int) -> IngestionJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)

        job.mark_running()
        self._jobs.update(job)

        try:
            draft = self._scraper.scrape(job.input_url)
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
