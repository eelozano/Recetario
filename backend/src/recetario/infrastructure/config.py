"""Configuration for the recipe-import helper.

The only knobs left are the Anthropic credentials: a well-structured page imports
with no key at all (deterministic recipe-scrapers pass); the key only unlocks the
LLM fallback, ingredient structuring, and video transcription. Keys are read from
the environment (`RECETARIO_*`) and from `~/.recetario/.env` — the packaged
helper's only source, since its working dir is `/`, not the repo.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_ENV_FILE = Path.home() / ".recetario" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECETARIO_",
        # Order matters: later files win. A dev-tree `.env` (CWD-relative) first,
        # then ~/.recetario/.env — the packaged helper's only source of keys (its
        # CWD is `/`, not backend/, so a relative `.env` is never found).
        env_file=(".env", str(_CONFIG_ENV_FILE)),
        extra="ignore",
    )

    # Anthropic API key. When set, import runs an extra LLM pass to structure
    # ingredient lines and to handle pages/videos the deterministic scraper can't.
    anthropic_api_key: str | None = None
    # Sonnet is the right tier: bounded extraction + tool-use, far cheaper/faster
    # than Opus with no meaningful quality loss. Override per-env.
    anthropic_model: str = "claude-sonnet-4-6"


def get_settings() -> Settings:
    return Settings()
