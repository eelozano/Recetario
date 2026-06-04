"""Sidecar entry point — the self-contained backend the desktop app launches.

Unlike `uvicorn recetario.api.main:app` (the dev workflow), this script is what
PyInstaller freezes into a single binary and Tauri runs as a sidecar. It does two
things the dev workflow leaves to the developer:

1. **Self-migrates** the user's database to head on startup, so a freshly
   installed app (or one upgraded across versions) always has the right schema
   without the user ever touching Alembic.
2. **Serves** the FastAPI app over the configured loopback host/port.

Run modes:
    python server.py            # from source (dev)
    ./recetario-server          # frozen binary (bundled by Tauri)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _alembic_dir() -> str:
    """Locate the bundled Alembic scripts in both source and frozen modes.

    PyInstaller unpacks bundled data under ``sys._MEIPASS``; from source the
    ``alembic/`` directory sits next to this file.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return str(base / "alembic")


def _run_migrations(settings) -> None:
    """Upgrade the configured database to head. env.py reads the URL straight
    from app settings, so we only need to point Alembic at the scripts."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", _alembic_dir())
    # The version scripts and env.py import the `recetario` package, which is
    # already importable (installed in dev, frozen in the binary).
    command.upgrade(cfg, "head")


def main() -> None:
    from recetario.infrastructure.config import get_settings

    settings = get_settings()  # also ensures the SQLite directory exists
    _run_migrations(settings)

    # Import the app only after migrations so the engine binds to a ready schema.
    import uvicorn

    from recetario.api.main import create_app

    app = create_app(settings)
    # Single worker, no reload: this is a local desktop sidecar, not a server farm.
    uvicorn.run(
        app,
        host=os.environ.get("RECETARIO_API_HOST", settings.api_host),
        port=int(os.environ.get("RECETARIO_API_PORT", settings.api_port)),
        log_level="info",
    )


if __name__ == "__main__":
    main()
