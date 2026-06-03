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
    StartUrlIngestion,
)
from recetario.application.use_cases.recipes import CreateRecipe
from recetario.infrastructure.db.repositories import (
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyNutritionRepository,
    SqlAlchemyRecipeRepository,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _build_enrich(request: Request, session) -> tuple[EnrichDraftRecipe | None, object | None]:
    """Assemble the optional LLM enricher for this job.

    Returns (enricher, provider). The provider (a live FDC client) is returned
    separately so the caller can close its HTTP connection after the job. Both
    are None unless an extractor *and* a nutrition provider are configured —
    USDA matching needs both, and enrichment is purely additive otherwise.
    """
    extractor_factory = getattr(request.app.state, "extractor_factory", None)
    provider_factory = getattr(request.app.state, "nutrition_provider_factory", None)
    extractor = extractor_factory() if extractor_factory else None
    provider = provider_factory() if provider_factory else None
    if extractor is None or provider is None:
        if provider is not None and hasattr(provider, "close"):
            provider.close()
        return None, None
    enrich = EnrichDraftRecipe(extractor, provider, SqlAlchemyNutritionRepository(session))
    return enrich, provider


def _run_job(request: Request, job_id: int) -> None:
    """Background worker: runs with its own DB session and scraper instance.

    The request-scoped session is already closed by the time this fires, so we
    open a fresh one from the app's session factory. The scraper comes from
    `app.state.scraper_factory`, which tests override to avoid live network.
    """
    session_factory = request.app.state.session_factory
    scraper_factory = request.app.state.scraper_factory
    session = session_factory()
    enrich, provider = _build_enrich(request, session)
    try:
        jobs = SqlAlchemyIngestionJobRepository(session)
        create_recipe = CreateRecipe(SqlAlchemyRecipeRepository(session))
        RunUrlIngestion(jobs, create_recipe, scraper_factory(), enrich)(job_id)
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
    job = uc(payload.url)
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
