"""Centralized configuration. The single knob that switches SQLite ↔ Postgres."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path.home() / ".recetario"
_DEFAULT_DB = _CONFIG_DIR / "recetario.db"
# The user config file the Settings panel writes to. It lives next to the DB —
# outside the repo and outside the app bundle — so each install (yours, a
# friend's) supplies its own keys.
_CONFIG_ENV_FILE = _CONFIG_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECETARIO_",
        # Order matters: later files win. A dev-tree `.env` (CWD-relative) first,
        # then ~/.recetario/.env — the packaged app's only source of keys (its
        # CWD is `/`, not backend/, so a relative `.env` is never found) and
        # where the in-app Settings panel saves. A key saved in the app thus
        # always wins over a stale checkout value.
        env_file=(".env", str(_CONFIG_ENV_FILE)),
        extra="ignore",
    )

    # Swap to e.g. "postgresql+psycopg://user:pass@host/db" for the cloud migration.
    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    # USDA FoodData Central API key (free, https://fdc.nal.usda.gov/api-key-signup.html).
    # Required only by the nutrition seeder / live lookups, not for normal app runtime.
    fdc_api_key: str | None = None

    # Anthropic API key. When set (alongside fdc_api_key), URL ingestion runs an
    # extra LLM pass to parse ingredient quantities and match USDA foods. Absent,
    # ingestion falls back to the deterministic scraper only.
    anthropic_api_key: str | None = None
    # Sonnet is the right tier for ingestion: bounded extraction + tool-use, far
    # cheaper/faster than Opus with no meaningful quality loss. Override per-env.
    anthropic_model: str = "claude-sonnet-4-6"

    # Google Tasks export (Phase 6). The client-secret JSON is the OAuth "Desktop
    # app" credential downloaded from Google Cloud; the key file holds the local
    # Fernet key used to encrypt stored OAuth tokens at rest. Both default under
    # ~/.recetario and are never committed.
    google_client_secret_file: str = str(Path.home() / ".recetario" / "google_client_secret.json")
    token_key_file: str = str(Path.home() / ".recetario" / "token.key")
    google_tasks_scopes: str = "https://www.googleapis.com/auth/tasks"

    # Where the in-app Settings panel persists user-entered keys. Same file this
    # Settings object reads on boot (see env_file above), so a save is picked up
    # on the next read with no separate config path to keep in sync.
    config_env_file: str = str(_CONFIG_ENV_FILE)

    def ensure_sqlite_dir(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            path = Path(self.database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_sqlite_dir()
    return settings
