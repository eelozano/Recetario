"""Alembic environment — pulls the DB URL from app settings and the metadata from
the ORM models so `alembic revision --autogenerate` stays in sync with the schema.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from recetario.infrastructure.config import get_settings
from recetario.infrastructure.db.base import Base
from recetario.infrastructure.db.session import create_db_engine

# Importing the models module registers all tables on Base.metadata.
from recetario.infrastructure.db import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(settings)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # batch mode keeps ALTERs working on SQLite
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
