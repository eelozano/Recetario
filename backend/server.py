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
import signal
import sys
import threading
import time
from pathlib import Path


def _pid_alive(pid: int) -> bool:
    """True while ``pid`` exists. ``kill(pid, 0)`` signals nothing but validates
    the target: ProcessLookupError means it's gone; PermissionError means it
    exists but isn't ours to signal (still "alive" for our purposes)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watch_tick(*, is_alive, on_dead) -> bool:
    """One watchdog check. Returns True (and calls ``on_dead``) once the watched
    process is gone. Pure and injectable so the orphan logic is unit-testable
    without tearing down a real process tree."""
    if not is_alive():
        on_dead()
        return True
    return False


def _terminate_self() -> None:
    """Ask uvicorn to shut down gracefully (SIGTERM), then hard-exit as a backstop."""
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)
    # uvicorn handles SIGTERM and unwinds; if it somehow hangs, force the exit.
    time.sleep(5)
    os._exit(0)


def _watch_loop(is_alive, *, interval: float = 1.0) -> None:
    while not _watch_tick(is_alive=is_alive, on_dead=_terminate_self):
        time.sleep(interval)


def _resolve_watch_target():
    """Pick the liveness check for the parent watchdog, or None if nothing to watch.

    Prefers the desktop app's PID passed in ``RECETARIO_PARENT_PID`` (set by the
    Tauri shell). That's essential under PyInstaller's one-file mode: the real
    Python process is a child of the *bootloader*, not of the app, so ``getppid``
    would track the bootloader (which itself gets orphaned but keeps running) and
    never notice the app dying. Watching the app PID's liveness directly avoids
    that. Falls back to ``getppid`` for the plain ``python server.py`` dev case.
    """
    env_pid = os.environ.get("RECETARIO_PARENT_PID", "").strip()
    if env_pid.isdigit():
        target = int(env_pid)
        return (lambda: _pid_alive(target)) if _pid_alive(target) else None

    parent_pid = os.getppid()
    if parent_pid <= 1:
        return None  # already orphaned at launch (or no real parent)
    return lambda: os.getppid() == parent_pid


def _start_parent_watchdog() -> None:
    """Exit when the desktop app that launched us dies.

    Tauri does **not** kill the sidecar when the app is force-quit or crashes: the
    orphaned backend is reparented to launchd and keeps holding the API port, so
    the next launch finds the port taken and serves a stale build. The Rust shell's
    exit handler only covers a *graceful* quit — it can't run when the app is
    SIGKILLed. This watchdog closes that gap from the child side, the only place
    that survives a force-killed parent.
    """
    is_alive = _resolve_watch_target()
    if is_alive is None:
        return
    threading.Thread(
        target=_watch_loop, args=(is_alive,), name="parent-watchdog", daemon=True
    ).start()


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

    # Don't outlive the desktop app that launched us (see _start_parent_watchdog).
    _start_parent_watchdog()

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
