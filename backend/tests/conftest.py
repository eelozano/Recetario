from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
