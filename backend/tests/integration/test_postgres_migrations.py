"""Opt-in: validate the Alembic migration chain on the target database.

The `client`/`db_engine` fixtures build the schema with ``create_all`` (fast), but
production builds it by *running the migrations*. This test closes that gap: it
runs ``alembic upgrade head`` from an empty database and asserts the full schema
appears — the real proof of the SQLite→Postgres swap.

Skipped entirely unless RECETARIO_TEST_DATABASE_URL is set (typically a throwaway
Postgres; see tests/conftest.py for the docker one-liner).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

TEST_DATABASE_URL = os.environ.get("RECETARIO_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set RECETARIO_TEST_DATABASE_URL to validate migrations on a real database",
)

# Keep in lockstep with the latest revision (alembic heads).
HEAD_REVISION = "f2a6d5e8c1b4"

# A representative slice of tables spanning every phase's migration.
EXPECTED_TABLES = {
    "recipes",
    "recipe_ingredients",
    "ingredients",
    "tags",
    "ingestion_jobs",
    "meal_events",
    "shopping_lists",
    "shopping_list_items",
    "oauth_credentials",
    "usda_foods",
    "usda_food_nutrients",
    "nutrients",
}


def _alembic_config():
    from alembic.config import Config

    cfg = Config()
    # backend/alembic — resolve from this file: integration → tests → backend.
    cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "alembic")
    )
    return cfg


def _drop_everything(engine) -> None:
    from recetario.infrastructure.db.base import Base

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_migration_chain_builds_full_schema(monkeypatch) -> None:
    # Alembic's env.py reads the URL from app settings (RECETARIO_DATABASE_URL),
    # so point that at the test database for the duration of this test.
    monkeypatch.setenv("RECETARIO_DATABASE_URL", TEST_DATABASE_URL)

    from alembic import command

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        _drop_everything(engine)  # start from a truly empty database

        cfg = _alembic_config()
        command.upgrade(cfg, "head")

        # The whole schema is present...
        tables = set(inspect(engine).get_table_names())
        missing = EXPECTED_TABLES - tables
        assert not missing, f"migrations left these tables unbuilt: {sorted(missing)}"

        # ...and the chain landed on the expected head revision.
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == HEAD_REVISION
    finally:
        _drop_everything(engine)
        engine.dispose()
