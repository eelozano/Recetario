"""Persist user-supplied secrets to the config env file the app reads on boot.

The in-app Settings panel needs somewhere to put a user's API keys that (a) lives
outside the repo and the app bundle, (b) is the same file `Settings` already
reads, and (c) survives upgrades. That's ~/.recetario/.env — next to the SQLite
DB. This adapter does a minimal, comment-preserving read/modify/write of that
dotenv file, writing it 0600 so the keys aren't world-readable.

It is deliberately dumb about precedence and validation: it only edits the lines
it manages and leaves everything else (e.g. a hand-set RECETARIO_DATABASE_URL or
comments) untouched.
"""

from __future__ import annotations

import os
from pathlib import Path


class EnvFileSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, str]:
        """Return the env vars currently set in the file (name -> value)."""
        result: dict[str, str] = {}
        for raw in self._lines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
        return result

    def update(self, changes: dict[str, str | None]) -> None:
        """Set or remove env vars, preserving unmanaged lines and comments.

        A value of ``None`` or ``""`` removes the key entirely (so "clear my key"
        leaves no empty assignment behind). The file is (re)written 0600.
        """
        # Normalize: empty string means delete.
        normalized = {k: (v if v else None) for k, v in changes.items()}
        managed = set(normalized)

        kept: list[str] = []
        seen: set[str] = set()
        for raw in self._lines():
            stripped = raw.strip()
            key = stripped.partition("=")[0].strip() if "=" in stripped else None
            if key in managed and not stripped.startswith("#"):
                seen.add(key)
                new_value = normalized[key]
                if new_value is not None:
                    kept.append(f"{key}={new_value}")
                # else: drop the line (removal)
            else:
                kept.append(raw.rstrip("\n"))

        # Append any newly-set keys that weren't already present.
        for key, value in normalized.items():
            if value is not None and key not in seen:
                kept.append(f"{key}={value}")

        self._write("\n".join(kept) + ("\n" if kept else ""))

    def _lines(self) -> list[str]:
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()

    def _write(self, content: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Owner-only perms from creation; re-chmod in case the file pre-existed.
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(self._path, 0o600)
