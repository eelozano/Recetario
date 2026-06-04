"""SQLAlchemy store for OAuth credentials, encrypted at rest via TokenCipher.

The connector hands us the provider's serialized credential JSON; we encrypt the
`encrypted_data` column on save and decrypt on read. Scopes/expiry are stored in
the clear for status display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from recetario.infrastructure.db.models import OAuthCredentialModel
from recetario.infrastructure.security import TokenCipher


@dataclass
class StoredCredential:
    data: str  # decrypted credential JSON
    scopes: str | None = None
    expires_at: datetime | None = None


class SqlAlchemyCredentialRepository:
    def __init__(self, session: Session, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    def get(self, provider: str) -> StoredCredential | None:
        model = self._session.scalar(
            select(OAuthCredentialModel).where(OAuthCredentialModel.provider == provider)
        )
        if model is None:
            return None
        return StoredCredential(
            data=self._cipher.decrypt(model.encrypted_data),
            scopes=model.scopes,
            expires_at=model.expires_at,
        )

    def save(
        self,
        provider: str,
        data: str,
        *,
        scopes: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        encrypted = self._cipher.encrypt(data)
        model = self._session.scalar(
            select(OAuthCredentialModel).where(OAuthCredentialModel.provider == provider)
        )
        if model is None:
            model = OAuthCredentialModel(provider=provider)
            self._session.add(model)
        model.encrypted_data = encrypted
        model.scopes = scopes
        model.expires_at = expires_at
        self._session.commit()

    def delete(self, provider: str) -> bool:
        model = self._session.scalar(
            select(OAuthCredentialModel).where(OAuthCredentialModel.provider == provider)
        )
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True
