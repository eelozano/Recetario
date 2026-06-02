"""Centralized configuration. The single knob that switches SQLite ↔ Postgres."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DB = Path.home() / ".recetario" / "recetario.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECETARIO_", env_file=".env", extra="ignore")

    # Swap to e.g. "postgresql+psycopg://user:pass@host/db" for the cloud migration.
    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    def ensure_sqlite_dir(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            path = Path(self.database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_sqlite_dir()
    return settings
