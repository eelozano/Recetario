from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from recetario.api.main import create_app
from recetario.infrastructure.db.base import Base
from recetario.infrastructure.db.session import create_session_factory


@pytest.fixture
def client() -> TestClient:
    # In-memory SQLite shared across connections for the duration of the test.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Mirror production (see db/session.py): enforce foreign keys so ON DELETE
    # CASCADE / SET NULL actually fire under SQLite.
    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    # Keep the suite hermetic regardless of the developer's .env: disable live
    # LLM/FDC enrichment by default. Tests that exercise the enrichment path
    # override these factories with stubs (see test_ingestion_enrich_api.py).
    app.state.extractor_factory = lambda: None
    app.state.nutrition_provider_factory = lambda: None
    return TestClient(app)
