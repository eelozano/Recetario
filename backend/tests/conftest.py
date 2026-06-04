from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from recetario.api.main import create_app
from recetario.infrastructure.db.base import Base
from recetario.infrastructure.db.session import create_session_factory

# --- Opt-in Postgres validation ---------------------------------------------
# By default the suite runs against a hermetic in-memory SQLite (fast, no infra).
# Set RECETARIO_TEST_DATABASE_URL to a Postgres URL, e.g.
#
#     RECETARIO_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/recetario_test \
#         .venv/bin/pytest
#
# and the *same* tests run against that database instead — proving the
# SQLite→Postgres swap (the persistence layer is behind ports, so nothing else
# changes). A throwaway Docker Postgres is the usual target:
#
#     docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
#
# Leave the variable unset and everyday `pytest` behaves exactly as before.
TEST_DATABASE_URL = os.environ.get("RECETARIO_TEST_DATABASE_URL")


def _make_engine() -> Engine:
    """A schema-fresh engine for a single test.

    Against the configured external database we drop+recreate every table so each
    test starts clean; against in-memory SQLite each engine is already pristine.
    """
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL, future=True)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return engine

    # In-memory SQLite shared across connections for the duration of the test.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Mirror production (see db/session.py): enforce foreign keys so ON DELETE
    # CASCADE / SET NULL actually fire under SQLite. (Postgres enforces FKs
    # natively, so this listener is SQLite-only.)
    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_engine() -> Engine:
    """A clean database engine per test. Shared by the API `client` fixture and
    the repository integration tests so both honor the Postgres opt-in."""
    engine = _make_engine()
    try:
        yield engine
    finally:
        if TEST_DATABASE_URL:
            # Leave the external database clean between/after tests.
            Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_engine: Engine) -> TestClient:
    app = create_app()
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    # Keep the suite hermetic regardless of the developer's .env: disable live
    # LLM/FDC enrichment by default. Tests that exercise the enrichment path
    # override these factories with stubs (see test_ingestion_enrich_api.py).
    app.state.extractor_factory = lambda: None
    app.state.nutrition_provider_factory = lambda: None
    return TestClient(app)
