"""TokenCipher — symmetric encryption for OAuth tokens stored in the DB.

For this local-first app the key lives in a 0600 file next to the database
(default ~/.recetario/token.key), generated on first use. This keeps the refresh
token from sitting in plaintext in the SQLite file (e.g. if it's copied or
synced). When the app graduates to a hosted/multi-user deployment, swap this for
a KMS-backed key without touching callers.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


class TokenCipher:
    def __init__(self, key_file: str | Path) -> None:
        self._fernet = Fernet(_load_or_create_key(Path(key_file)))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


def _load_or_create_key(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    # Write with owner-only permissions (0600) from the start.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key
