"""Unit tests for the sidecar's parent-death watchdog (server.py).

server.py lives at the backend root (it's the frozen entry point, not part of the
importable `recetario` package), so we load it by path. We only exercise the pure
decision tick and the liveness/target helpers — never the real terminate path —
so no process is harmed.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_SERVER_PATH = Path(__file__).resolve().parents[2] / "server.py"
_spec = importlib.util.spec_from_file_location("recetario_server", _SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(server)


# --- _watch_tick: the pure decision ----------------------------------------


def test_tick_is_a_noop_while_target_is_alive():
    fired: list[int] = []
    dead = server._watch_tick(is_alive=lambda: True, on_dead=lambda: fired.append(1))
    assert dead is False
    assert fired == []


def test_tick_fires_once_target_is_gone():
    fired: list[int] = []
    dead = server._watch_tick(is_alive=lambda: False, on_dead=lambda: fired.append(1))
    assert dead is True
    assert fired == [1]


# --- _pid_alive -------------------------------------------------------------


def test_pid_alive_true_for_self():
    assert server._pid_alive(os.getpid()) is True


def test_pid_alive_false_for_unused_pid():
    # PID 2**31-1 is effectively never allocated; treat as gone.
    assert server._pid_alive(2**31 - 1) is False


# --- _resolve_watch_target: env PID preferred, getppid fallback -------------


def test_resolve_prefers_env_parent_pid_when_alive(monkeypatch):
    monkeypatch.setenv("RECETARIO_PARENT_PID", str(os.getpid()))
    is_alive = server._resolve_watch_target()
    assert is_alive is not None
    assert is_alive() is True  # our own PID is alive


def test_resolve_returns_none_when_env_pid_already_dead(monkeypatch):
    monkeypatch.setenv("RECETARIO_PARENT_PID", str(2**31 - 1))
    # A dead target at launch means nothing to watch (don't exit immediately).
    assert server._resolve_watch_target() is None


def test_resolve_falls_back_to_getppid_without_env(monkeypatch):
    monkeypatch.delenv("RECETARIO_PARENT_PID", raising=False)
    monkeypatch.setattr(server.os, "getppid", lambda: 4242)
    is_alive = server._resolve_watch_target()
    assert is_alive is not None
    assert is_alive() is True  # getppid still 4242
    # Simulate reparenting away from the original parent.
    monkeypatch.setattr(server.os, "getppid", lambda: 1)
    assert is_alive() is False


def test_resolve_returns_none_when_orphaned_at_launch(monkeypatch):
    monkeypatch.delenv("RECETARIO_PARENT_PID", raising=False)
    monkeypatch.setattr(server.os, "getppid", lambda: 1)
    assert server._resolve_watch_target() is None
