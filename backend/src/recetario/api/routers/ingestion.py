"""Recipe-ingestion endpoints.

`POST /ingestion/jobs` records a queued job and schedules the scrape as a
background task, returning 202 immediately. The UI polls `GET /ingestion/jobs/{id}`
until the job reaches `succeeded` (with `result_recipe_id`) or `failed`.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from recetario.api import deps
from recetario.api.schemas import IngestionJobCreate, IngestionJobOut
from recetario.application.use_cases.ingestion import (
    EnrichDraftRecipe,
    GetIngestionJob,
    IngestionJobNotFoundError,
    ListIngestionJobs,
    RunUrlIngestion,
    RunVideoIngestion,
    StartUrlIngestion,
)
from recetario.application.use_cases.recipes import CreateRecipe
from recetario.domain.entities import IngestionInputType
from recetario.infrastructure.db.repositories import (
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyNutritionRepository,
    SqlAlchemyRecipeRepository,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _build_components(request: Request, session):
    """Assemble the optional LLM extractor, FDC provider, and enricher.

    Returns `(extractor, provider, enrich)`. The extractor alone drives video
    extraction; the enricher (extractor + provider) drives USDA matching and is
    None unless both are configured. The live provider is returned so the caller
    can close its HTTP connection after the job. If a provider was opened without
    an extractor that could use it, it's closed here and returned as None.
    """
    extractor_factory = getattr(request.app.state, "extractor_factory", None)
    provider_factory = getattr(request.app.state, "nutrition_provider_factory", None)
    extractor = extractor_factory() if extractor_factory else None
    provider = provider_factory() if provider_factory else None

    if extractor is not None and provider is not None:
        enrich = EnrichDraftRecipe(
            extractor, provider, SqlAlchemyNutritionRepository(session)
        )
        return extractor, provider, enrich

    if extractor is None and provider is not None and hasattr(provider, "close"):
        provider.close()
        provider = None
    return extractor, provider, None


def _run_job(request: Request, job_id: int) -> None:
    """Background worker: runs with its own DB session and adapter instances.

    The request-scoped session is already closed by the time this fires, so we
    open a fresh one from the app's session factory. The job's `input_type`
    selects the web (scraper) or video (yt-dlp + LLM) pipeline. Adapter factories
    on `app.state` are overridden by tests to avoid live network/LLM calls.
    """
    session = request.app.state.session_factory()
    extractor, provider, enrich = _build_components(request, session)
    try:
        jobs = SqlAlchemyIngestionJobRepository(session)
        create_recipe = CreateRecipe(SqlAlchemyRecipeRepository(session))
        job = jobs.get(job_id)
        if job is None:
            return

        if job.input_type is IngestionInputType.VIDEO:
            if extractor is None:
                job.mark_failed(
                    "Video import requires an Anthropic API key "
                    "(set RECETARIO_ANTHROPIC_API_KEY)."
                )
                jobs.update(job)
                return
            fetcher = request.app.state.video_fetcher_factory()
            RunVideoIngestion(jobs, create_recipe, fetcher, extractor, enrich)(job_id)
        else:
            scraper = request.app.state.scraper_factory()
            RunUrlIngestion(jobs, create_recipe, scraper, enrich)(job_id)
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()
        session.close()


@router.post("/jobs", response_model=IngestionJobOut, status_code=status.HTTP_202_ACCEPTED)
def create_ingestion_job(
    payload: IngestionJobCreate,
    background: BackgroundTasks,
    request: Request,
    uc: StartUrlIngestion = Depends(deps.start_ingestion_uc),
):
    job = uc(payload.url, payload.input_type)
    background.add_task(_run_job, request, job.id)
    return IngestionJobOut.from_domain(job)


@router.get("/jobs", response_model=list[IngestionJobOut])
def list_ingestion_jobs(uc: ListIngestionJobs = Depends(deps.list_ingestion_jobs_uc)):
    return [IngestionJobOut.from_domain(j) for j in uc()]


@router.get("/jobs/{job_id}", response_model=IngestionJobOut)
def get_ingestion_job(job_id: int, uc: GetIngestionJob = Depends(deps.get_ingestion_job_uc)):
    try:
        return IngestionJobOut.from_domain(uc(job_id))
    except IngestionJobNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
