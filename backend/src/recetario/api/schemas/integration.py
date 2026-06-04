"""Pydantic models for the integrations (Google Tasks export) boundary."""

from __future__ import annotations

from pydantic import BaseModel


class IntegrationStatusOut(BaseModel):
    provider: str
    connected: bool
    # Whether the OAuth client-secret file is present, i.e. setup is possible.
    client_configured: bool
