"""Pydantic models for the Settings (BYO API keys) boundary.

The cardinal rule here: secrets go *in* but never come back *out*. The status
response exposes only whether a key is set and a short masked hint — never the
key itself — so a user's keys never reach the webview, devtools, or the network
log.
"""

from __future__ import annotations

from pydantic import BaseModel


class SecretStatus(BaseModel):
    configured: bool
    # A short, non-reversible hint so the user can tell *which* key is saved
    # (e.g. "…aZ9q") — the last 4 chars only, never the full value.
    hint: str | None = None


class SettingsStatusOut(BaseModel):
    fdc_api_key: SecretStatus
    anthropic_api_key: SecretStatus
    anthropic_model: str


class SettingsUpdateIn(BaseModel):
    """A partial update. Per-field semantics rely on which keys are *present*:
    a field omitted from the body is left unchanged; sent as an empty string it
    is cleared; sent with a value it is set. (The router inspects
    ``model_fields_set`` to tell "omitted" from "explicitly cleared".)"""

    fdc_api_key: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
