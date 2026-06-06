"""FastAPI app factory — the headless local API the Tauri UI talks to."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session

from recetario.api.factories import make_extractor_factory, make_provider_factory
from recetario.api.routers import (
    health,
    ingestion,
    integrations,
    meals,
    nutrition,
    recipes,
    settings as settings_router,
    shopping,
)
from recetario.application.ports import TaskExporter
from recetario.infrastructure.config import Settings, get_settings
from recetario.infrastructure.db.session import create_db_engine, create_session_factory
from recetario.infrastructure.scraping import RecipeScrapersAdapter
from recetario.infrastructure.settings_store import EnvFileSettingsStore
from recetario.infrastructure.video import YtDlpTranscriptFetcher


def _make_task_exporter_factory(settings: Settings):
    """Build a Google Tasks exporter per request, backed by the session's encrypted
    credential store. The Fernet cipher is created lazily so tests that override
    this factory never touch the on-disk key."""
    scopes = settings.google_tasks_scopes.split()
    cipher_box: list = []

    def build(session: Session) -> TaskExporter:
        from recetario.infrastructure.db.repositories import SqlAlchemyCredentialRepository
        from recetario.infrastructure.export import GoogleTasksConnector
        from recetario.infrastructure.security import TokenCipher

        if not cipher_box:
            cipher_box.append(TokenCipher(settings.token_key_file))
        store = SqlAlchemyCredentialRepository(session, cipher_box[0])
        return GoogleTasksConnector(
            store,
            client_secret_file=settings.google_client_secret_file,
            scopes=scopes,
        )

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
    # The Settings router rebuilds these on app.state when a user saves a key, so
    # enabling enrichment takes effect without a restart.
    app.state.extractor_factory = make_extractor_factory(settings)
    app.state.nutrition_provider_factory = make_provider_factory(settings)
    # Where the in-app Settings panel persists user keys (this is also the file
    # `Settings` reads on boot — see config.py).
    app.state.settings_store = EnvFileSettingsStore(settings.config_env_file)
    # Google Tasks export (Phase 6); tests override with a fake exporter.
    app.state.task_exporter_factory = _make_task_exporter_factory(settings)

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
    app.include_router(integrations.router)
    app.include_router(settings_router.router)
    return app


app = create_app()
