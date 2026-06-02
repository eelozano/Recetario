"""FastAPI app factory — the headless local API the Tauri UI talks to."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from recetario.api.routers import health, nutrition, recipes
from recetario.infrastructure.config import Settings, get_settings
from recetario.infrastructure.db.session import create_db_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Recetario API", version="0.1.0")

    engine = create_db_engine(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

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
    return app


app = create_app()
