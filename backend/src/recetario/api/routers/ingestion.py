"""Recipe-ingestion endpoints.

`POST /ingestion/jobs` records a queued job and schedules the scrape as a
background task, returning 202 immediately. The UI polls `GET /ingestion/jobs/{id}`
until the job reaches `succeeded` (with `result_recipe_id`) or `failed`.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from recetario.api import deps
from recetario.api.schemas import (
    IngestionJobCreate,
    IngestionJobFromHtml,
    IngestionJobOut,
)
from recetario.application.use_cases.ingestion import (
    EnrichDraftRecipe,
    GetIngestionJob,
    IngestionJobNotFoundError,
    ListIngestionJobs,
    RunHtmlIngestion,
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
from recetario.infrastructure.scraping import html_to_text

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _make_extractor(request: Request):
    """The optional LLM extractor, or None when no Anthropic key is configured."""
    factory = getattr(request.app.state, "extractor_factory", None)
    return factory() if factory else None


def _make_provider(request: Request):
    """The optional live FDC provider, or None when no FDC key is configured."""
    factory = getattr(request.app.state, "nutrition_provider_factory", None)
    return factory() if factory else None


def _run_web_job(request: Request, session, jobs, create_recipe, job_id: int) -> None:
    """Deterministic-first web import: scrape, falling back to the LLM only when
    scraping fails and an Anthropic key is configured."""
    extractor = _make_extractor(request)
    scraper = request.app.state.scraper_factory()
    # The page-text fetch is only needed for the LLM fallback path.
    fetch_page_text = getattr(scraper, "fetch_page_text", None) if extractor else None
    RunUrlIngestion(
        jobs,
        create_recipe,
        scraper,
        extractor=extractor,
        fetch_page_text=fetch_page_text,
    )(job_id)


def _run_html_job(request: Request, job_id: int, html: str) -> None:
    """Background worker for the in-app-browser import: parse caller-supplied HTML.

    Mirrors `_run_job`/`_run_web_job` (own DB session, deterministic-first with an
    optional LLM fallback) but skips the network fetch — the HTML was already
    captured by the in-app WebView and is handed in directly.
    """
    session = request.app.state.session_factory()
    try:
        jobs = SqlAlchemyIngestionJobRepository(session)
        create_recipe = CreateRecipe(SqlAlchemyRecipeRepository(session))
        extractor = _make_extractor(request)
        scraper = request.app.state.scraper_factory()
        RunHtmlIngestion(
            jobs,
            create_recipe,
            scraper,
            html,
            extractor=extractor,
            html_to_text=html_to_text if extractor else None,
        )(job_id)
    finally:
        session.close()


def _run_video_job(request: Request, session, jobs, create_recipe, job) -> None:
    """Video import: captions → LLM (required) → optional USDA enrichment."""
    extractor = _make_extractor(request)
    if extractor is None:
        job.mark_failed(
            "Video import requires an Anthropic API key "
            "(set RECETARIO_ANTHROPIC_API_KEY)."
        )
        jobs.update(job)
        return

    provider = _make_provider(request)
    enrich = (
        EnrichDraftRecipe(extractor, provider, SqlAlchemyNutritionRepository(session))
        if provider is not None
        else None
    )
    try:
        fetcher = request.app.state.video_fetcher_factory()
        RunVideoIngestion(jobs, create_recipe, fetcher, extractor, enrich)(job.id)
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()


def _run_job(request: Request, job_id: int) -> None:
    """Background worker: runs with its own DB session and adapter instances.

    The request-scoped session is already closed by the time this fires, so we
    open a fresh one from the app's session factory. The job's `input_type`
    selects the web (deterministic scraper, LLM fallback) or video (captions +
    LLM) pipeline. Adapter factories on `app.state` are overridden by tests to
    avoid live network/LLM calls.
    """
    session = request.app.state.session_factory()
    try:
        jobs = SqlAlchemyIngestionJobRepository(session)
        create_recipe = CreateRecipe(SqlAlchemyRecipeRepository(session))
        job = jobs.get(job_id)
        if job is None:
            return

        if job.input_type is IngestionInputType.VIDEO:
            _run_video_job(request, session, jobs, create_recipe, job)
        else:
            _run_web_job(request, session, jobs, create_recipe, job_id)
    finally:
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


@router.post(
    "/jobs/from-html",
    response_model=IngestionJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_ingestion_job_from_html(
    payload: IngestionJobFromHtml,
    background: BackgroundTasks,
    request: Request,
    uc: StartUrlIngestion = Depends(deps.start_ingestion_uc),
):
    """Import a recipe from HTML captured by the in-app browser.

    Used for bot-protected pages (e.g. Cloudflare JS challenges) that a
    server-side fetch can't get past: the in-app WebView renders the page as a
    real browser, then the captured HTML is parsed here with no network fetch.
    Always treated as a web page (videos use the URL path).
    """
    job = uc(payload.url, IngestionInputType.WEB)
    background.add_task(_run_html_job, request, job.id, payload.html)
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
