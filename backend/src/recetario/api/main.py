"""FastAPI app factory — the headless local API the Tauri UI talks to."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from recetario.api.routers import health, ingestion, meals, nutrition, recipes, shopping
from recetario.application.ports import LlmRecipeExtractor, NutritionProvider
from recetario.infrastructure.config import Settings, get_settings
from recetario.infrastructure.db.session import create_db_engine, create_session_factory
from recetario.infrastructure.scraping import RecipeScrapersAdapter
from recetario.infrastructure.video import YtDlpTranscriptFetcher


def _make_extractor_factory(
    settings: Settings,
) -> Callable[[], LlmRecipeExtractor | None]:
    """LLM enrichment is opt-in: only built when an Anthropic key is configured."""
    if not settings.anthropic_api_key:
        return lambda: None

    def build() -> LlmRecipeExtractor | None:
        from recetario.infrastructure.llm import AnthropicRecipeExtractor

        return AnthropicRecipeExtractor(
            settings.anthropic_api_key, model=settings.anthropic_model
        )

    return build


def _make_provider_factory(
    settings: Settings,
) -> Callable[[], NutritionProvider | None]:
    """USDA matching needs the live FDC provider; absent a key, it's unavailable."""
    if not settings.fdc_api_key:
        return lambda: None

    def build() -> NutritionProvider | None:
        from recetario.infrastructure.nutrition.fdc_client import UsdaFdcClient

        return UsdaFdcClient(settings.fdc_api_key)

    return build


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Recetario API", version="0.1.0")

    engine = create_db_engine(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    # Background ingestion builds a scraper (web) or transcript fetcher (video)
    # from these factories; tests override them with fakes to stay offline.
    app.state.scraper_factory = RecipeScrapersAdapter
    app.state.video_fetcher_factory = YtDlpTranscriptFetcher
    # Optional LLM enrichment of scraped drafts. Both factories return None when
    # their API key is absent; tests override them to exercise the path offline.
    app.state.extractor_factory = _make_extractor_factory(settings)
    app.state.nutrition_provider_factory = _make_provider_factory(settings)

    # The Tauri/web client is a separate origin during dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(recipes.router)
    app.include_router(recipes.tags_router)
    app.include_router(nutrition.router)
    app.include_router(ingestion.router)
    app.include_router(meals.router)
    app.include_router(shopping.router)
    return app


app = create_app()
